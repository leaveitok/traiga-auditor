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
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.collectors import procurement

PROVENANCE = "discovered_oauth"

# Grant fields we carry into evidence. Deliberately excludes anything user-identifying.
_EVIDENCE_FIELDS = ("app_id", "publisher", "provider", "scopes_joined",
                    "scope_sensitivity", "scope_reaches", "user_count",
                    "first_seen", "last_seen")


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
        row = {
            # The app name is the vendor signal; publisher helps disambiguate.
            "vendor":            (g.get("app_name") or "").strip(),
            "product":           (g.get("app_name") or "").strip(),
            "city":              city,
            "app_id":            str(g.get("app_id") or "").strip(),
            "publisher":         (g.get("publisher") or "").strip(),
            "provider":          (g.get("provider") or "").strip(),
            "scopes_joined":     ", ".join(str(s) for s in scopes),
            "scope_sensitivity": cls["sensitivity"],
            "scope_reaches":     "; ".join(cls["reaches"]),
            "user_count":        str(count),
            "first_seen":        str(g.get("first_seen") or ""),
            "last_seen":         str(g.get("last_seen") or ""),
        }
        if include_users and users:
            # Opt-in only, and clearly named so it is auditable downstream.
            row["consenting_users"] = ", ".join(str(u) for u in users)
        rows.append(row)

    extra = _EVIDENCE_FIELDS + (("consenting_users",) if include_users else ())
    return procurement.normalize(
        rows, index, city_field="city", min_confidence=mc,
        provenance=PROVENANCE,
        extra_evidence_fields=extra,
    )
