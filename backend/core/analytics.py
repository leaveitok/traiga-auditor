"""
analytics.py — PURE aggregation for the Analytics page (no I/O, storage-agnostic).

Takes the repo reads (scorecard, violations, ai_assets) and returns a dashboard
dict. The headline is VENDOR PREVALENCE across cities — "how many of your cities
run each AI tool" — the cross-jurisdiction intelligence no single-tenant
competitor can produce. The route fetches + RBAC-scopes, then calls this.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

# Cure-clock aging buckets (days remaining).
_CURE_BUCKETS = [("0-15 days", 0, 15), ("16-30 days", 16, 30),
                 ("31-45 days", 31, 45), ("46-60 days", 46, 60)]


def _int(v: Any):
    try:
        return int(float(str(v)))
    except (ValueError, TypeError):
        return None


def build_analytics(scorecard: List[Dict[str, Any]],
                    violations: List[Dict[str, Any]],
                    ai_assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    sc = scorecard or []
    vio = violations or []
    assets = ai_assets or []

    status = Counter(str(r.get("traiga_status", "not_assessed")) for r in sc)
    scores = [s for s in (_int(r.get("compliance_score")) for r in sc) if s is not None]

    # Vendor prevalence: distinct cities per canonical tool (the moat metric).
    tools: Dict[str, Dict[str, Any]] = {}
    for a in assets:
        tid = a.get("tool_id") or a.get("vendor_id") or "unknown"
        entry = tools.setdefault(tid, {
            "tool_id": tid,
            "display_name": a.get("display_name") or tid,
            "cities": set(),
        })
        if a.get("city"):
            entry["cities"].add(a["city"])
    prevalence = sorted(
        ({"tool_id": t["tool_id"], "display_name": t["display_name"],
          "city_count": len(t["cities"])} for t in tools.values()),
        key=lambda x: (-x["city_count"], x["display_name"]))[:15]

    provenance = Counter(str(a.get("provenance", "unknown")) for a in assets)
    lifecycle = Counter(str(a.get("lifecycle_status", "discovered")) for a in assets)

    aging: Dict[str, int] = {b[0]: 0 for b in _CURE_BUCKETS}
    aging["expired"] = 0
    for v in vio:
        st = str(v.get("status", "")).lower()
        if st == "cured":
            continue
        dr = _int(v.get("days_remaining"))
        if st == "expired" or (dr is not None and dr < 0):
            aging["expired"] += 1
            continue
        if dr is None:
            continue
        for name, lo, hi in _CURE_BUCKETS:
            if lo <= dr <= hi:
                aging[name] += 1
                break

    return {
        "totals": {
            "cities":          len(sc),
            "ai_assets":       len(assets),
            "open_violations": sum(1 for v in vio if str(v.get("status", "")).lower() != "cured"),
            "attested":        sum(1 for a in assets if a.get("lifecycle_status") == "attested"),
            "needs_attestation": sum(1 for a in assets if a.get("lifecycle_status") == "discovered"),
            "avg_score":       round(sum(scores) / len(scores), 1) if scores else None,
        },
        "status_distribution":  dict(status),
        "vendor_prevalence":    prevalence,
        "provenance_breakdown": dict(provenance),
        "lifecycle_breakdown":  dict(lifecycle),
        "cure_aging":           aging,
    }
