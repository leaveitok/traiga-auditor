"""
procurement_source.py — procurement discovery ORCHESTRATOR.

Takes already-parsed rows (the route/frontend handles file upload + CSV parse,
reusing the bulk-import pattern) + a GovernanceRepository, builds the tool index
from the schema, runs the PURE normalizer, and merges. Mirrors
sentinel_feed.sync_to_inventory (the existing channel orchestrator).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from engine import rule_loader
from engine.collectors import procurement
from engine.collectors.identity import build_tool_index
from core.discovery.merge import merge_discovered_assets

PROVENANCE = procurement.PROVENANCE


def run_procurement_discovery(
    repo: Any,
    rows: List[Dict[str, Any]],
    *,
    vendor_field: str = "vendor",
    city_field: str = "city",
    default_city: str = "",
    min_confidence: float = procurement.DEFAULT_MIN_CONFIDENCE,
    allowed_cities: Optional[Set[str]] = None,   # None = platform admin (all cities)
    actor: str = "system",
) -> Dict[str, Any]:
    """
    Discover procured AI from vendor/spend/contract rows and merge into ai_assets.
    Returns {written, matched, skipped, rows, cities, errors}.

    TODO: enforce system/admin-only invocation (auth placeholder — route enforces).
    """
    schema = rule_loader.load_schema()
    index = build_tool_index(schema)
    result = procurement.normalize(
        rows, index, vendor_field=vendor_field, city_field=city_field,
        default_city=default_city, min_confidence=min_confidence,
    )

    # Fail-secure tenancy: an agency user can only write assets for its own cities.
    if allowed_cities is not None:
        kept = [a for a in result["assets"] if a.get("city") in allowed_cities]
        result["skipped"] += len(result["assets"]) - len(kept)
        result["assets"] = kept

    merged = merge_discovered_assets(repo, result)

    try:
        repo.append_audit_log(
            event="discovery_procurement",
            city_count=len(merged["cities"]),
            failures=result["skipped"],
            details={
                "actor":   actor,
                "summary": f"Procurement discovery: {merged['written']} AI vendors matched "
                           f"across {len(merged['cities'])} cities ({result['skipped']} rows skipped)",
                "matched": result["source_meta"]["matched"],
                "skipped": result["skipped"],
                "cities":  ", ".join(merged["cities"]),
            },
        )
    except Exception as exc:
        print(f"[discovery] WARN: could not log procurement run: {exc}")

    return {
        **merged,
        "matched": result["source_meta"]["matched"],
        "candidates": result["source_meta"].get("candidates", 0),
        "rows": result["source_meta"]["rows"],
    }
