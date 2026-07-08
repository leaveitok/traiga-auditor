"""
sentinel_feed.py — inside-out discovery: Sentinel DLP telemetry → AI inventory.

The scanner finds AI on the city's PUBLIC surface (outside-in). Sentinel
observes employee AI usage in the browser fleet (inside-out). This feed joins
them in one registry: usage of ChatGPT/Claude/Gemini/etc. becomes an ai_assets
row with provenance="discovered_sentinel", carrying usage and DLP-block counts
as evidence. Together they answer the question competitors' cloud-tenant
"agent discovery" cannot: what AI does this CITY actually touch?

Rules:
  - Metadata only, same as Sentinel itself: rows carry counts and site ids,
    never prompt text (the ingest layer already enforces this).
  - Merge contract preserved: this feed writes MACHINE fields only through the
    merge-preserving upsert_ai_asset; owner/purpose/cid_* are never touched.
  - Fail-secure scoping: events without a city tag are NOT attributed to any
    city — they are counted and reported as skipped, never guessed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

# Known Sentinel site ids → human labels. Fallback: title-cased site_id.
SITE_LABELS = {
    "chatgpt":    "ChatGPT",
    "openai":     "ChatGPT",
    "claude":     "Claude",
    "gemini":     "Google Gemini",
    "copilot":    "Microsoft Copilot",
    "perplexity": "Perplexity",
    "grok":       "Grok",
}


def _label(site_id: str) -> str:
    return SITE_LABELS.get(site_id.lower(), site_id.replace("_", " ").title() or "Unknown AI tool")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_usage_assets(events: List[Dict[str, Any]],
                       heartbeats: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Group Sentinel telemetry into per-(city, site) usage asset payloads.
    Returns {assets: [...], skipped_untagged: int, cities: [...]}.
    """
    groups: Dict[tuple, Dict[str, Any]] = {}
    skipped = 0
    for e in events:
        city = str(e.get("city", "")).strip()
        site = str(e.get("site_id", "")).strip().lower()
        if not city or not site:
            skipped += 1
            continue
        key = (city, site)
        g = groups.setdefault(key, {
            "event_count": 0, "blocked_count": 0,
            "devices": set(), "policies": set(), "last_seen": "",
        })
        g["event_count"] += 1
        if str(e.get("action", "")).lower() in ("block", "blocked"):
            g["blocked_count"] += 1
        if e.get("device_id") or e.get("user_id"):
            g["devices"].add(e.get("device_id") or e.get("user_id"))
        if e.get("policy_id"):
            g["policies"].add(str(e.get("policy_id")))
        ts = str(e.get("timestamp_utc") or e.get("received_utc") or "")
        if ts > g["last_seen"]:
            g["last_seen"] = ts

    # Device fleet context per city (heartbeats carry city + device ids)
    fleet: Dict[str, set] = {}
    for h in heartbeats:
        c = str(h.get("city", "")).strip()
        if c and (h.get("device_id") or h.get("user_id")):
            fleet.setdefault(c, set()).add(h.get("device_id") or h.get("user_id"))

    assets: List[Dict[str, Any]] = []
    for (city, site), g in sorted(groups.items()):
        assets.append({
            "asset_key":        f"sentinel:{site}@{city}",
            "city":             city,
            "provenance":       "discovered_sentinel",
            "display_name":     f"{_label(site)} — staff usage",
            "vendor_id":        site,
            "asset_types_json": '["genai_tool", "staff_usage"]',
            "page_url":         "",   # internal usage: no public URL
            "last_observed_utc": g["last_seen"] or _now_iso(),
            "presence":          "observed",
            "sentinel_event_count":   str(g["event_count"]),
            "sentinel_blocked_count": str(g["blocked_count"]),
            "sentinel_device_count":  str(len(g["devices"])),
            "sentinel_policies":      ",".join(sorted(g["policies"])),
            "sentinel_fleet_devices": str(len(fleet.get(city, set()))),
            "evidence_note": (f"Observed via Sentinel browser DLP: {g['event_count']} events "
                              f"({g['blocked_count']} blocked) across {len(g['devices'])} devices."),
        })
    return {
        "assets": assets,
        "skipped_untagged": skipped,
        "cities": sorted({a["city"] for a in assets}),
    }


def sync_to_inventory(gov_repo: Any, sentinel_repo: Any,
                      event_limit: int = 1000) -> Dict[str, Any]:
    """Pull telemetry, build usage assets, merge-upsert into the registry."""
    events = sentinel_repo.get_events(limit=event_limit)
    heartbeats = sentinel_repo.get_heartbeats(limit=500)
    built = build_usage_assets(events, heartbeats)
    written = 0
    errors: List[str] = []
    for asset in built["assets"]:
        try:
            gov_repo.upsert_ai_asset(asset)   # merge-preserving; human fields untouched
            written += 1
        except Exception as exc:
            errors.append(f"{asset['asset_key']}: {type(exc).__name__}")
    return {
        "synced": written,
        "cities": built["cities"],
        "skipped_untagged_events": built["skipped_untagged"],
        "errors": errors,
    }
