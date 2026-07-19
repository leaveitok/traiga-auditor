"""
oauth_source.py — OAuth / shadow-AI discovery ORCHESTRATOR (I/O + merge).

Takes already-parsed OAuth grant records — from a customer-run export file the admin
uploaded (Door A, no credentials shared) or, later, a live read-only API sync (Door B) —
runs the PURE normalizer, and merges into ai_assets as provenance=discovered_oauth.

Two safety properties this module owns, because a pilot runs in a REAL tenant:

  * DRY RUN (default ON for a tenant's first run): compute and report the findings but
    write NOTHING. The city sees exactly what would be recorded before anything is
    persisted. `written` is 0 and `dry_run` is echoed in the result.
  * FAIL-SECURE on an empty/partial fetch: an empty grant list is treated as "no data"
    (a no-op), never as "this city has no AI". Absence of evidence is not evidence of
    absence — the same rule the scanner uses for a blocked crawl.

Privacy: employee identities are dropped by engine.collectors.oauth unless the caller
opts in; this orchestrator never asks for them. See docs/OAUTH_DISCOVERY_DESIGN.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from engine import rule_loader
from engine.collectors import oauth
from engine.collectors.identity import build_tool_index
from core.discovery.merge import merge_discovered_assets

PROVENANCE = oauth.PROVENANCE


def _disabled_result(reason: str) -> Dict[str, Any]:
    return {"written": 0, "matched": 0, "candidates": 0, "skipped": 0, "rows": 0,
            "cities": [], "errors": [reason], "dry_run": False}


def run_oauth_discovery(
    repo: Any,
    city: str,
    grants: List[Dict[str, Any]],
    *,
    provider: str = "",
    dry_run: bool = True,
    include_users: bool = False,
    min_confidence: Optional[float] = None,
    allowed_cities: Optional[Set[str]] = None,   # None = platform admin (all cities)
    actor: str = "system",
) -> Dict[str, Any]:
    """
    Discover shadow AI from OAuth grant records and merge into ai_assets.
    Returns {written, matched, candidates, skipped, rows, cities, errors, dry_run}.

    TODO: enforce system/admin-only invocation (auth placeholder — the route enforces).
    TODO: scope to the requesting user's jurisdiction (auth placeholder).
    """
    from core import settings
    if not settings.get_bool(repo, "OAUTH_DISCOVERY_ENABLED"):
        return _disabled_result("oauth_discovery_disabled")

    # Fail-secure tenancy: an agency user can only write assets for its own cities.
    if allowed_cities is not None and city not in allowed_cities:
        return _disabled_result("city_out_of_scope")

    # Fail-secure emptiness: no records is "we learned nothing", not "this city is clean".
    if not grants:
        return {"written": 0, "matched": 0, "candidates": 0, "skipped": 0, "rows": 0,
                "cities": [], "errors": ["no_grants_supplied"], "dry_run": dry_run}

    schema = rule_loader.load_schema()
    index = build_tool_index(schema)
    scope_rules = schema.get("OAuth_Scope_Sensitivity", {})

    # Stamp the provider so evidence records where the grant came from.
    rows = [{**g, "provider": (g.get("provider") or provider or "")} for g in grants]

    result = oauth.normalize(
        rows, index, city, scope_rules=scope_rules,
        min_confidence=min_confidence, include_users=include_users,
    )

    meta = result.get("source_meta", {})
    base = {
        "matched":    meta.get("matched", 0),
        "candidates": meta.get("candidates", 0),
        "rows":       meta.get("rows", len(rows)),
        "skipped":    result.get("skipped", 0),
        "dry_run":    dry_run,
    }

    if dry_run:
        # Report only. Nothing is written; the city approves first.
        cities = sorted({a.get("city", "") for a in result.get("assets", []) if a.get("city")})
        out = {**base, "written": 0, "cities": cities, "errors": []}
        _log(repo, city, out, actor, dry_run=True)
        return out

    merged = merge_discovered_assets(repo, result)
    out = {**base, "written": merged["written"], "skipped": merged.get("skipped", base["skipped"]),
           "cities": merged["cities"], "errors": merged.get("errors", [])}
    _log(repo, city, out, actor, dry_run=False)
    return out


def _log(repo: Any, city: str, out: Dict[str, Any], actor: str, *, dry_run: bool) -> None:
    """Audit every run — including dry runs, which are still access to tenant data."""
    try:
        repo.append_audit_log(
            event="discovery_oauth",
            city_count=len(out.get("cities", [])),
            failures=out.get("skipped", 0),
            details={
                "actor":   actor,
                "summary": (f"OAuth discovery for {city}: "
                            f"{'DRY RUN — nothing written, ' if dry_run else ''}"
                            f"{out.get('matched', 0)} matched, "
                            f"{out.get('candidates', 0)} for review "
                            f"from {out.get('rows', 0)} grant(s)"),
                "dry_run":    dry_run,
                "matched":    out.get("matched", 0),
                "candidates": out.get("candidates", 0),
                "rows":       out.get("rows", 0),
            },
        )
    except Exception as exc:
        print(f"[discovery] WARN: could not log oauth run for {city}: "
              f"{type(exc).__name__}: {exc}")
