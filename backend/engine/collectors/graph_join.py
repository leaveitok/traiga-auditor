"""
graph_join.py — PURE join of raw Microsoft Graph output into grant records (engine/).

WHY THIS EXISTS. Many municipal shops run endpoint protection, AppLocker, WDAC or
Constrained Language Mode that blocks PowerShell scripts outright. Those cities cannot
run our export script at all, and the usual workaround — a .bat that calls
`powershell -ExecutionPolicy Bypass` — is the signature move of commodity malware, so it
makes quarantine MORE likely and asks a security team to weaken a control in order to run
a compliance tool. Not a trade we should offer.

The alternative is to execute nothing on the endpoint. The administrator signs into
Microsoft Graph Explorer — Microsoft's own first-party web tool — runs two GET queries and
downloads the JSON:

    GET /v1.0/servicePrincipals?$select=id,appId,displayName,publisherName,signInAudience
    GET /v1.0/oauth2PermissionGrants

Our script performs the join between those two locally; this module performs the SAME join
server-side so the browser path produces byte-identical grant records. That makes the
script optional convenience rather than a hard dependency, and puts the join in the tested
layer either way.

Storage-agnostic and provider-agnostic by the engine/ rule: dicts in, dicts out.

Reference:
  https://learn.microsoft.com/en-us/graph/api/oauth2permissiongrant-list?view=graph-rest-1.0
  https://learn.microsoft.com/en-us/graph/api/resources/serviceprincipal?view=graph-rest-1.0
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Graph returns collections as {"value": [...]}, with @odata.nextLink when paged.
_VALUE = "value"
_NEXT = "@odata.nextLink"


def _rows(blob: Any) -> List[Dict[str, Any]]:
    """Accept a Graph collection response, or a bare list, or a single object."""
    if blob is None:
        return []
    if isinstance(blob, list):
        return [r for r in blob if isinstance(r, dict)]
    if isinstance(blob, dict):
        if isinstance(blob.get(_VALUE), list):
            return [r for r in blob[_VALUE] if isinstance(r, dict)]
        # A single resource pasted on its own.
        if blob.get("id") or blob.get("appId") or blob.get("clientId"):
            return [blob]
    return []


def looks_like_graph_payload(blob: Any) -> bool:
    """Is this raw Graph output rather than our script's export?

    Our script emits {"grants": [...]}; Graph emits {"value": [...]}. Checking for the
    absence of 'grants' as well as the presence of 'value' keeps the two unambiguous even
    if a future script version gains a value field.
    """
    if not isinstance(blob, dict):
        return False
    if "grants" in blob:
        return False
    return isinstance(blob.get(_VALUE), list) or _NEXT in blob


def classify_graph_file(blob: Any) -> str:
    """'service_principals' | 'permission_grants' | 'unknown'.

    The admin downloads two files and cannot reasonably be expected to label which is
    which, so we identify them by shape. A servicePrincipal has appId/displayName; an
    oAuth2PermissionGrant has clientId/consentType/scope.
    """
    rows = _rows(blob)
    if not rows:
        return "unknown"
    sp_hits = sum(1 for r in rows[:50] if "appId" in r or "displayName" in r)
    gr_hits = sum(1 for r in rows[:50] if "clientId" in r or "consentType" in r or "scope" in r)
    if gr_hits > sp_hits:
        return "permission_grants"
    if sp_hits > 0:
        return "service_principals"
    return "unknown"


def is_paged(blob: Any) -> bool:
    """True if Graph signalled more results than this file contains.

    Graph Explorer returns one page (100 by default) and shows a nextLink. An admin who
    downloads only the first page would silently under-report their tenant, which for a
    compliance product is the worst kind of wrong — it looks like a clean result. Callers
    must surface this rather than swallow it.
    """
    return isinstance(blob, dict) and bool(blob.get(_NEXT))


def join_graph_exports(
    service_principals: Any,
    permission_grants: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """PURE: raw Graph collections -> the same grant records our export script emits.

    Mirrors the script exactly:
      * group by the service principal's appId (the stable, portable identifier),
      * union the space-delimited scope strings across every grant for that app,
      * consentType 'Principal' counts ONE consenting user (by principalId),
        consentType 'AllPrincipals' means an admin consented tenant-wide,
      * a grant whose clientId matches no service principal is skipped, exactly as the
        script skips it — we cannot name the app, so reporting it would be noise.

    PRIVACY: principalIds are counted, never returned. This function has no opt-in to
    return them, because the browser path has no legitimate need for identities and the
    narrower surface is the safer one.

    Returns (grants, meta) where meta explains what was dropped and why.
    """
    sp_rows = _rows(service_principals)
    grant_rows = _rows(permission_grants)

    # id -> service principal. Grants reference the SP's object id via clientId.
    by_object_id: Dict[str, Dict[str, Any]] = {}
    for sp in sp_rows:
        oid = str(sp.get("id") or "").strip()
        if oid:
            by_object_id[oid] = sp

    by_app: Dict[str, Dict[str, Any]] = {}
    users_by_app: Dict[str, set] = {}
    unresolved = 0

    for g in grant_rows:
        client_id = str(g.get("clientId") or "").strip()
        sp = by_object_id.get(client_id)
        if not sp:
            # Grant for an app absent from the servicePrincipals file — usually because
            # only one page was downloaded, or the two files came from different tenants.
            unresolved += 1
            continue

        key = str(sp.get("appId") or client_id)
        rec = by_app.get(key)
        if rec is None:
            rec = {
                "app_id":           sp.get("appId") or "",
                "app_name":         sp.get("displayName") or "",
                "publisher":        sp.get("publisherName") or "",
                "provider":         "microsoft",
                "sign_in_audience": sp.get("signInAudience") or "",
                "scopes":           [],
                "user_count":       0,
            }
            by_app[key] = rec
            users_by_app[key] = set()

        for s in str(g.get("scope") or "").split():
            s = s.strip()
            if s and s not in rec["scopes"]:
                rec["scopes"].append(s)

        consent = str(g.get("consentType") or "").strip().lower()
        if consent == "allprincipals":
            rec["tenant_wide_admin_consent"] = True
        else:
            pid = str(g.get("principalId") or "").strip()
            if pid:
                users_by_app[key].add(pid)

    for key, rec in by_app.items():
        rec["scopes"] = sorted(rec["scopes"])
        rec["user_count"] = len(users_by_app.get(key, ()))

    grants = sorted(by_app.values(), key=lambda r: (r.get("app_name") or "").lower())
    meta = {
        "service_principals_seen": len(sp_rows),
        "permission_grants_seen":  len(grant_rows),
        "apps_joined":             len(grants),
        # Non-zero almost always means a partial download. Surfaced, never swallowed.
        "grants_without_matching_app": unresolved,
        "service_principals_paged": is_paged(service_principals),
        "permission_grants_paged":  is_paged(permission_grants),
    }
    return grants, meta
