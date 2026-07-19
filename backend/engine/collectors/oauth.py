"""
oauth.py — PURE OAuth / shadow-AI normalizer (engine/, no HTTP, no repo, no LLM).

Turns provider-agnostic OAuth grant records — "someone in this tenant consented to app X,
which can reach Y" — into discovered AI assets via the SHARED procurement matcher, with
provenance=discovered_oauth. Serves BOTH front doors identically:
  * a customer-run export file the admin uploads (no credentials shared), and
  * a live read-only API sync (opt-in),
because by the time records reach here they are the same shape. See
docs/OAUTH_DISCOVERY_DESIGN.md.

PRIVACY (enforced here, not left to callers): user identities are DROPPED unless the caller
explicitly opts in. This is employee-monitoring data — the default answer to "who consented"
is a COUNT, not a list of names. The pure layer is the right place to enforce that, because
then no orchestrator or route can leak identities by forgetting a flag.

Governance: we report what a grant can REACH (scopes -> sensitivity, from
SCHEMA_DEFINITION.json OAuth_Scope_Sensitivity). We never compute a risk score.

Signature harvest: apps we FAIL to recognise are returned as `unmatched` — the raw
material for new catalog entries. A partner city's single export is the only way to
learn real Entra display names, publisher strings and (for multi-tenant apps) stable
app IDs, so throwing the misses away would waste the most valuable half of the run.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.collectors import procurement

PROVENANCE = "discovered_oauth"

# Grant fields we carry into evidence. Deliberately excludes anything user-identifying.
_EVIDENCE_FIELDS = ("app_id", "publisher", "provider", "scopes_joined",
                    "scope_sensitivity", "scope_reaches", "user_count",
                    "first_seen", "last_seen", "tenant_wide_admin_consent",
                    "sign_in_audience")

# Everything needed to AUTHOR a catalog signature from a real tenant observation, so a
# partner city's single run yields a usable backlog instead of just a count. Mirrors the
# alias shape in SCHEMA_DEFINITION.json AI_Tool_Catalog.
_SIGNATURE_FIELDS = ("app_name", "app_id", "publisher", "provider", "scopes_joined",
                     "scope_sensitivity", "user_count", "tenant_wide_admin_consent",
                     "sign_in_audience", "catalog_promotable")

# Entra signInAudience values meaning the application is MULTI-TENANT: the same appId
# identifies the same vendor app in every tenant on earth, so an ID observed at one city
# is safe and useful to promote into the shared catalog. AzureADMyOrg, by contrast, is an
# app registered inside that one tenant — its appId is meaningless elsewhere and must
# never be written into a catalog shared across cities.
_MULTI_TENANT_AUDIENCES = {"azureadmultipleorgs", "azureadandpersonalmicrosoftaccount"}

# Corporate legal suffixes carry no identifying information, but they DO wreck token-set
# matching: "Grammarly, Inc." vs the catalog alias "grammarly" scores 0.5 with the suffix
# and 1.0 without it. Stripped from the PUBLISHER only.
_CORP_SUFFIXES = {
    "inc", "incorporated", "llc", "l.l.c", "llp", "lp", "ltd", "limited", "co",
    "company", "corp", "corporation", "pbc", "plc", "gmbh", "ag", "sa", "sas",
    "bv", "nv", "pty", "srl", "spa", "oy", "ab", "as", "kk", "kg", "holdings",
}


def clean_publisher(publisher: str) -> str:
    """PURE: strip trailing corporate legal suffixes from a publisher name.

    WHY THIS MATTERS. Real Entra display names carry qualifiers a catalog alias never
    does — "Grammarly for Windows", "Fireflies.ai Notetaker" — so matching on the app
    NAME alone misses vendors we already know about. (Verified against a realistic
    export fixture: "Grammarly for Windows" scored 0.333 against alias "grammarly" and
    fell through as unrecognised.)

    The publisher is the better signal: it is the verified company behind the app, and
    it does not carry product qualifiers. The only thing in its way is the legal suffix.

    Deliberately NOT solved by relaxing the shared matcher. The tempting fix — award a
    match whenever the alias tokens are fully contained in the observed name — was tested
    and rejected: it matches "grok" inside "AI Consulting Services from Grok Partners
    LLC" and "claude" inside "Claude Monet Art Archive". Publisher matching produced zero
    cross-vendor hits on the same test (Adobe scored 0.000 against grammarly).
    """
    toks = [t for t in str(publisher or "").replace(",", " ").split() if t.strip()]
    while toks and toks[-1].strip(".").lower() in _CORP_SUFFIXES:
        toks.pop()
    return " ".join(toks).strip()


def is_catalog_promotable(sign_in_audience: str, provider: str = "") -> bool:
    """PURE: may this app's ID be promoted into the SHARED vendor catalog?

    Only multi-tenant Microsoft apps qualify. Anything unknown returns False — a wrong
    ID silently mis-attributes an app to the wrong vendor for every city that follows,
    which is far worse than a missing one. Fail closed.
    """
    aud = str(sign_in_audience or "").strip().lower()
    if not aud:
        return False
    return aud in _MULTI_TENANT_AUDIENCES


def classify_scopes(scopes: List[str], rules_block: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    PURE: granted scopes -> {sensitivity, reaches[], write}. First matching rule wins per
    scope; the highest tier across all scopes is the grant's tier. A write-capable scope
    escalates one tier (a app that can CHANGE mail is not the same as one that can read it).
    Unknown/unmatched scopes yield 'unknown' rather than a guessed tier.
    """
    order = {"low": 0, "medium": 1, "high": 2}
    rules = (rules_block or {}).get("rules", []) or []
    esc = ((rules_block or {}).get("write_escalation") or {}).get("pattern") or ""

    best = -1
    reaches: List[str] = []
    write = False
    seen_any = False

    for raw in (scopes or []):
        s = str(raw or "").strip()
        if not s:
            continue
        if esc:
            try:
                if re.search(esc, s):
                    write = True
            except re.error:
                pass
        for r in rules:
            pat = r.get("pattern")
            if not pat:
                continue
            try:
                if re.search(pat, s):
                    seen_any = True
                    tier = r.get("tier", "low")
                    if order.get(tier, 0) > best:
                        best = order.get(tier, 0)
                    why = r.get("reaches")
                    if why and why not in reaches:
                        reaches.append(why)
                    break
            except re.error:
                continue

    if not seen_any:
        return {"sensitivity": "unknown", "reaches": [], "write": write}

    if write and best < order["high"]:
        best += 1
    sensitivity = [k for k, v in order.items() if v == best]
    return {"sensitivity": (sensitivity[0] if sensitivity else "unknown"),
            "reaches": reaches, "write": write}


def normalize(grants: List[Dict[str, Any]], index: Dict[str, Any], city: str,
              scope_rules: Optional[Dict[str, Any]] = None,
              min_confidence: Optional[float] = None,
              include_users: bool = False) -> Dict[str, Any]:
    """
    grants: provider-agnostic records, each
      {app_id, app_name, publisher, scopes[], user_count, provider, first_seen, last_seen}
      (a provider client maps Microsoft oauth2PermissionGrants / Google token records
      into this shape; this function never talks to a provider.)

    Delegates matching to the SHARED procurement matcher so an app found here resolves to
    the SAME canonical tool_id as the same app found by scan/procurement/agenda — one
    registry row, multi-source evidence.

    include_users=False (default) DROPS any user identities present on the input.
    TODO: enforce system-level invocation only (auth placeholder).
    """
    mc = procurement.DEFAULT_MIN_CONFIDENCE if min_confidence is None else min_confidence
    rows: List[Dict[str, Any]] = []

    for g in (grants or []):
        scopes = list(g.get("scopes") or [])
        cls = classify_scopes(scopes, scope_rules)
        # user_count is a COUNT; derive it from a user list only to count it, never to store it.
        users = g.get("users") or []
        count = g.get("user_count")
        if count is None:
            count = len(users) if users else ""
        audience = str(g.get("sign_in_audience") or "").strip()
        app_name = (g.get("app_name") or "").strip()
        publisher_raw = (g.get("publisher") or "").strip()
        row = {
            # Two independent match targets, both tried by the shared matcher (best wins):
            #   product = the app display name  ("Grammarly for Windows")
            #   vendor  = the cleaned publisher ("Grammarly")
            # The publisher is what rescues vendors whose Entra display name carries a
            # product qualifier the catalog alias does not have.
            "vendor":            clean_publisher(publisher_raw) or app_name,
            "product":           app_name,
            "app_name":          app_name,
            "city":              city,
            "app_id":            str(g.get("app_id") or "").strip(),
            "publisher":         publisher_raw,
            "provider":          (g.get("provider") or "").strip(),
            "scopes_joined":     ", ".join(str(s) for s in scopes),
            "scope_sensitivity": cls["sensitivity"],
            "scope_reaches":     "; ".join(cls["reaches"]),
            "user_count":        str(count),
            "first_seen":        str(g.get("first_seen") or ""),
            "last_seen":         str(g.get("last_seen") or ""),
            "sign_in_audience":  audience,
            # Promotability is decided HERE, in the pure layer, so no UI or orchestrator
            # can accidentally offer a tenant-local app ID for the shared catalog.
            "catalog_promotable": "yes" if is_catalog_promotable(audience) else "no",
        }
        # Tenant-wide admin consent: an administrator approved this app on behalf of the
        # WHOLE organisation, so no individual employee ever agreed to it. It is the
        # highest-severity thing an OAuth export can tell you, and it was previously
        # computed by the export script and then silently dropped here.
        if g.get("tenant_wide_admin_consent"):
            row["tenant_wide_admin_consent"] = "yes"
        if include_users and users:
            # Opt-in only, and clearly named so it is auditable downstream.
            row["consenting_users"] = ", ".join(str(u) for u in users)
        rows.append(row)

    extra = _EVIDENCE_FIELDS + (("consenting_users",) if include_users else ())
    return procurement.normalize(
        rows, index, city_field="city", min_confidence=mc,
        provenance=PROVENANCE,
        extra_evidence_fields=extra,
        # Harvest what we did NOT recognise. Note this deliberately never includes
        # consenting_users: an app we cannot identify is exactly the case where leaking
        # who used it would be least defensible.
        collect_unmatched=_SIGNATURE_FIELDS,
    )
