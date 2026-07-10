"""
identity.py — canonical tool-identity resolver (PURE; storage-agnostic, no I/O).

THE PROBLEM IT SOLVES: the same AI tool found by different channels must become
ONE registry row, not several. The website scanner keys by vendor_id, Sentinel by
site id, procurement by a free-text vendor name, OAuth by an app id. This module
maps any channel's raw identifier to ONE canonical `tool_id`.

GOVERNANCE-AS-CODE: aliases live in SCHEMA_DEFINITION.json, never in code —
  - AI_Tool_Catalog.tools[]      → SaaS/AI tools (OpenAI, Copilot, Gemini, …)
  - AI_Vendor_Fingerprints.vendors[] vendor_ids are ALSO valid canonical tool_ids
    (a website hit's vendor_id is canonical by definition).

Runs identically in the content of a collector and in Node/py unit tests.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# The alias buckets a tool can declare, one per discovery channel.
# procurement_names = how the VENDOR/company appears on a contract;
# product_names     = how the PRODUCT/line-item appears (disambiguates multi-product
#                     vendors, e.g. "Microsoft" -> Office vs "Copilot" -> AI).
ALIAS_CHANNELS = ("sentinel_site_ids", "oauth_app_ids", "domains",
                  "procurement_names", "product_names")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def build_tool_index(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the lookup index used by every channel's resolver.

    Returns:
      {
        "by_alias": { channel: { normalized_alias: tool_id } },
        "by_name":  { normalized_name_or_id: tool_id },
        "procurement_candidates": [ (normalized_string, tool_id) ],  # for fuzzy match
      }
    """
    by_alias: Dict[str, Dict[str, str]] = {c: {} for c in ALIAS_CHANNELS}
    by_name: Dict[str, str] = {}
    proc_candidates: List[Tuple[str, str]] = []

    def _register(tool_id: str, display_name: str, aliases: Dict[str, Any]) -> None:
        if not tool_id:
            return
        by_name.setdefault(_norm(tool_id), tool_id)
        by_name.setdefault(_norm(display_name or tool_id), tool_id)
        proc_candidates.append((_norm(display_name or tool_id), tool_id))
        proc_candidates.append((_norm(tool_id), tool_id))
        for ch in ALIAS_CHANNELS:
            for a in (aliases.get(ch) or []):
                by_alias[ch].setdefault(_norm(a), tool_id)
                # Both the vendor name and the product name are match candidates
                # for procurement/agenda text (which mixes company + line-item).
                if ch in ("procurement_names", "product_names"):
                    proc_candidates.append((_norm(a), tool_id))

    # 1) Canonical SaaS/AI tool catalog.
    for t in ((schema.get("AI_Tool_Catalog") or {}).get("tools") or []):
        _register(t.get("tool_id", ""), t.get("display_name", ""), t.get("aliases") or {})

    # 2) Fingerprint vendors — their vendor_id is a valid canonical tool_id.
    for v in ((schema.get("AI_Vendor_Fingerprints") or {}).get("vendors") or []):
        _register(v.get("vendor_id", ""), v.get("display_name", ""), v.get("aliases") or {})

    ai_keywords = [_norm(k) for k in
                   ((schema.get("AI_Tool_Catalog") or {}).get("ai_keywords") or []) if _norm(k)]

    return {"by_alias": by_alias, "by_name": by_name,
            "procurement_candidates": proc_candidates,
            "ai_keywords": ai_keywords}


def resolve_tool_id(channel: str, raw_id: Any, index: Dict[str, Any]) -> str:
    """
    Map a raw identifier from `channel` to a canonical tool_id.

    Exact alias match first, then an exact name/id match as a cross-channel
    fallback. Unresolved ids return "unknown:<raw>" — SURFACED for human triage,
    never silently dropped (fail-secure).
    """
    raw = _norm(raw_id)
    if not raw:
        return "unknown:blank"
    hit = index.get("by_alias", {}).get(channel, {}).get(raw)
    if hit:
        return hit
    hit = index.get("by_name", {}).get(raw)
    if hit:
        return hit
    return f"unknown:{raw}"
