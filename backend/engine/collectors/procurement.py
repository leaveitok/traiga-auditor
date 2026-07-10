"""
procurement.py — procurement/contract discovery normalizer (PURE; no I/O).

Turns rows from an uploaded vendor master / AP spend / contract register into
DiscoveredAsset dicts, matched against the tool catalog. A procured AI vendor is
a strong "should be in the inventory" signal that no website scan or browser
watch can see. Also seeds the vendor-risk module.

Matching: token-set overlap against the catalog's procurement_names aliases +
display names (exact alias = full confidence). A confidence FLOOR prevents junk
matches; rows with no confident AI match are counted as `skipped` — SURFACED,
never guessed into a tool (fail-secure).

Consumes the index from engine.collectors.identity.build_tool_index — no import
of it here, so this stays trivially unit-testable in isolation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

PROVENANCE = "discovered_procurement"
DEFAULT_MIN_CONFIDENCE = 0.5


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _tokens(s: Any) -> set:
    return set(re.findall(r"[a-z0-9]+", _norm(s)))


def _token_set_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _match(raw_vendor: str, candidates: List) -> tuple:
    """Best (tool_id, confidence) over catalog candidates. Exact alias -> 1.0."""
    raw = _norm(raw_vendor)
    best_id, best = None, 0.0
    for cand_name, tool_id in candidates:
        if raw == cand_name:
            return tool_id, 1.0
        r = _token_set_ratio(raw, cand_name)
        if r > best:
            best, best_id = r, tool_id
    return best_id, round(best, 3)


def normalize(
    rows: List[Dict[str, Any]],
    index: Dict[str, Any],
    vendor_field: str = "vendor",
    city_field: str = "city",
    default_city: str = "",
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Dict[str, Any]:
    """
    rows: parsed file rows (dicts). The route/orchestrator handles file parsing;
    this function is pure. Returns a DiscoveryResult dict.
    """
    candidates = index.get("procurement_candidates", [])
    assets: List[Dict[str, Any]] = []
    skipped = 0
    for row in rows:
        raw_vendor = (row.get(vendor_field) or row.get("vendor_name")
                      or row.get("supplier") or "").strip()
        city = (row.get(city_field) or default_city or "").strip()
        if not raw_vendor or not city:
            skipped += 1
            continue
        tool_id, conf = _match(raw_vendor, candidates)
        if not tool_id or conf < min_confidence:
            skipped += 1          # not a confident AI-vendor match -> surfaced as skipped
            continue
        evidence = {k: row[k] for k in ("contract_id", "amount", "term", "department")
                    if row.get(k) not in (None, "")}
        evidence["vendor_name_raw"] = raw_vendor
        assets.append({
            "tool_id":      tool_id,
            "vendor_id":    tool_id,
            "city":         city,
            "display_name": raw_vendor,
            "asset_types":  ["procured_ai"],
            "provenance":   PROVENANCE,
            "confidence":   conf,
            "evidence":     evidence,
            # NOTE: no `presence` — a contract is a procured signal, not observed
            # live usage. Presence stays whatever an observing channel set.
        })
    return {
        "assets": assets,
        "skipped": skipped,
        "source_meta": {"rows": len(rows), "matched": len(assets)},
    }
