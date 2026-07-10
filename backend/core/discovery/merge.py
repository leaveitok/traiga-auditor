"""
merge.py — merge DiscoveredAssets into the ai_assets registry.

The single write path for EVERY discovery channel. Uses the repository's
merge-preserving upsert_ai_asset, so MACHINE fields refresh while human fields
(owner, attestation, purpose, cid_*, lifecycle) are never touched.

MULTI-SOURCE UNION (the canonical-identity payoff): the same tool found by
several channels becomes ONE row whose `discovery_sources_json` lists every
channel that found it ("scan + Sentinel + procurement"). `provenance` retains the
FIRST (primary) source for backward compatibility. Because upsert_ai_asset
overwrites fields, this helper reads existing sources and unions them before
writing — exactly how engine.pipeline._feed_inventory reads existing rows first.

Batch-tolerant: one bad row never aborts the run (mirrors sentinel_feed).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(s: Any) -> str:
    return str(s).strip().lower().replace(" ", "-").replace("/", "_")


def asset_key(city: str, tool_id: str) -> str:
    """Canonical registry key: one row per (city, tool). Shared across channels."""
    return f"{_safe(city)}::{_safe(tool_id or 'unknown')}"


def _to_record(a: Dict[str, Any], key: str, prior: Dict[str, Any] | None) -> Dict[str, Any]:
    now = a.get("observed_utc") or _now()
    prov = a.get("provenance", "declared")
    tool_id = a.get("tool_id") or a.get("vendor_id") or "unknown"

    # Union discovery sources: replace this channel's prior entry (refresh), keep others.
    sources: List[Dict[str, Any]] = []
    if prior and prior.get("discovery_sources_json"):
        try:
            sources = json.loads(prior["discovery_sources_json"]) or []
        except (ValueError, TypeError):
            sources = []
    sources = [s for s in sources if s.get("provenance") != prov]
    sources.append({"provenance": prov, "observed_utc": now, "evidence": a.get("evidence", {})})

    record: Dict[str, Any] = {
        "asset_key":              key,
        "city":                   a.get("city", ""),
        "tool_id":                tool_id,
        "vendor_id":              a.get("vendor_id") or tool_id,
        "display_name":           a.get("display_name", ""),
        "asset_types_json":       json.dumps(a.get("asset_types", []) or []),
        # provenance = FIRST source (preserve prior); only set for a brand-new row.
        "provenance":             (prior.get("provenance") if prior and prior.get("provenance") else prov),
        "discovery_sources_json": json.dumps(sources),
        "last_observed_utc":      now,
        "match_confidence":       str(a.get("confidence", "")),
        "evidence_json":          json.dumps(a.get("evidence", {})),
    }
    # presence only when the channel actually observed the tool live.
    if a.get("presence"):
        record["presence"] = a["presence"]
    # New rows are born discovered; existing rows keep their human lifecycle.
    if not prior:
        record["first_observed_utc"] = now
        record["lifecycle_status"] = "discovered"
    return record


def merge_discovered_assets(repo: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upsert every DiscoveredAsset in `result` into ai_assets (merge-preserving).
    Returns {written, cities, skipped, errors}.
    TODO: enforce system-level write only (auth placeholder).
    """
    assets = result.get("assets", []) or []

    # Pre-read existing rows once per city to union discovery_sources.
    existing_by_key: Dict[str, Dict[str, Any]] = {}
    for city in {a.get("city") for a in assets if a.get("city")}:
        try:
            for r in repo.get_ai_assets(city=city):
                existing_by_key[r.get("asset_key")] = r
        except Exception:
            pass   # a read failure just means no prior sources to union

    written = 0
    cities = set()
    errors: List[str] = []
    for a in assets:
        try:
            key = asset_key(a.get("city", ""), a.get("tool_id") or a.get("vendor_id", ""))
            repo.upsert_ai_asset(_to_record(a, key, existing_by_key.get(key)))
            written += 1
            if a.get("city"):
                cities.add(a["city"])
        except Exception as exc:
            errors.append(f"{a.get('tool_id', '?')}@{a.get('city', '?')}: {type(exc).__name__}")

    return {
        "written": written,
        "cities": sorted(cities),
        "skipped": result.get("skipped", 0),
        "errors": errors,
    }
