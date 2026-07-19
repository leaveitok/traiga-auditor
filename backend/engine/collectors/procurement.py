"""
procurement.py — procurement/contract discovery normalizer (PURE; no I/O).

Turns rows from an uploaded vendor master / AP spend / contract register (or, in
future, extracted council-agenda contract-award items) into DiscoveredAsset
dicts, matched against the tool catalog.

WHY BOTH VENDOR AND PRODUCT: the AI signal often lives in the product/line-item,
not the company name. "OpenAI" (vendor == product) is easy; but "Tyler
Technologies — AI permitting assistant" or "Microsoft — Copilot" need the PRODUCT
field. So we match against vendor AND product text, and if neither resolves to a
catalog tool we run an AI-KEYWORD SCREEN over the combined text: a line item that
says "AI assistant" surfaces as a CANDIDATE (unknown tool, flagged for human
review) rather than being dropped — fail-secure, and the whole point of the
channel is catching AI you don't yet have a fingerprint for.

Consumes the index from engine.collectors.identity.build_tool_index. No import of
it here, so this stays trivially unit-testable in isolation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

PROVENANCE = "discovered_procurement"

# Cap on the signature-harvest list. A tenant with thousands of consented apps must not
# turn one API response into a multi-megabyte payload; the flag below reports truncation.
MAX_UNMATCHED_REPORTED = 200
DEFAULT_MIN_CONFIDENCE = 0.5

VENDOR_FIELDS  = ("vendor", "supplier", "vendor_name", "company", "payee")
PRODUCT_FIELDS = ("product", "description", "line_item", "service", "item", "purpose")

# Fallback AI-keyword list (the schema's AI_Tool_Catalog.ai_keywords overrides/extends).
# Matched with word boundaries so "ai" is a word, not a substring of "maintenance".
DEFAULT_AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "generative ai", "genai",
    "large language model", "llm", "gpt", "chatbot", "virtual assistant",
    "conversational ai", "natural language", "computer vision", "facial recognition",
    "predictive analytics", "automated decision", "copilot", "neural network",
    "deep learning", "cognitive services",
]


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _tokens(s: Any) -> set:
    return set(re.findall(r"[a-z0-9]+", _norm(s)))


def _token_set_ratio(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _match(text: str, candidates: List) -> tuple:
    """Best (tool_id, confidence) over catalog candidates. Exact alias -> 1.0."""
    raw = _norm(text)
    if not raw:
        return None, 0.0
    best_id, best = None, 0.0
    for cand_name, tool_id in candidates:
        if raw == cand_name:
            return tool_id, 1.0
        r = _token_set_ratio(raw, cand_name)
        if r > best:
            best, best_id = r, tool_id
    return best_id, round(best, 3)


def _first(row: Dict[str, Any], names) -> str:
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _keyword_hit(text: str, keywords: List[str]) -> Optional[str]:
    """Return the first AI keyword present (word-boundary match), else None."""
    hay = _norm(text)
    for kw in keywords:
        if kw and re.search(r"\b" + re.escape(kw) + r"\b", hay):
            return kw
    return None


def normalize(
    rows: List[Dict[str, Any]],
    index: Dict[str, Any],
    vendor_field: str = "vendor",
    city_field: str = "city",
    default_city: str = "",
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    provenance: str = PROVENANCE,
    extra_evidence_fields: tuple = (),
    collect_unmatched: tuple = (),
) -> Dict[str, Any]:
    """
    rows: parsed file/agenda rows (dicts). Pure — the orchestrator handles I/O.
    Returns a DiscoveryResult dict; source_meta carries matched vs candidate counts.

    Reused by other channels (e.g. council-agenda award items): pass
    provenance="discovered_agenda" and extra_evidence_fields to carry that
    channel's evidence (meeting_date, item_title, source_url, action) through.

    collect_unmatched: field names to carry into a returned `unmatched` list.

      WHY THIS EXISTS. A row that matches no catalog entry and trips no AI keyword is
      counted in `skipped` and then thrown away. That is fine for a customer, who only
      wants to know what WAS found — but it discards exactly the information needed to
      grow the catalog. When a partner city runs a discovery channel, the apps we FAILED
      to recognise are the most valuable output of the run: each one is a candidate
      signature, and a signature added benefits every city afterwards. Losing them costs
      a whole round-trip with a partner who is doing us a favour.

      Opt-in and empty by default, so every existing caller keeps its current behaviour
      and payload size. Only channels that are explicitly harvesting signatures ask for it.
    """
    candidates = index.get("procurement_candidates", [])
    keywords = index.get("ai_keywords") or DEFAULT_AI_KEYWORDS
    assets: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    skipped = 0

    for row in rows:
        vendor_text  = (row.get(vendor_field) or _first(row, VENDOR_FIELDS) or "").strip()
        product_text = _first(row, PRODUCT_FIELDS)
        city = (row.get(city_field) or default_city or "").strip()
        if not (vendor_text or product_text) or not city:
            skipped += 1
            continue

        display = product_text or vendor_text
        _ev_keys = ("contract_id", "amount", "term", "department") + tuple(extra_evidence_fields)
        evidence = {k: row[k] for k in _ev_keys if row.get(k) not in (None, "")}
        if vendor_text:
            evidence["vendor_name_raw"] = vendor_text
        if product_text:
            evidence["product_raw"] = product_text

        # 1) Catalog match across BOTH the product and the vendor text; best wins.
        best_id, best_conf = None, 0.0
        for text in (product_text, vendor_text):
            tid, conf = _match(text, candidates)
            if tid and conf > best_conf:
                best_id, best_conf = tid, conf

        if best_id and best_conf >= min_confidence:
            assets.append({
                "tool_id":      best_id,
                "vendor_id":    best_id,
                "city":         city,
                "display_name": display,
                "asset_types":  ["procured_ai"],
                "provenance":   provenance,
                "confidence":   best_conf,
                "evidence":     {**evidence, "match_type": "catalog"},
            })
            continue

        # 2) AI-keyword screen (surface, don't drop): a line item that says "AI"
        #    becomes a CANDIDATE for human review — even from an unknown vendor.
        kw = _keyword_hit(f"{vendor_text} {product_text}", keywords)
        if kw:
            assets.append({
                "tool_id":      f"unknown:ai:{_norm(display)[:60] or 'unnamed'}",
                "vendor_id":    "",
                "city":         city,
                "display_name": display,
                "asset_types":  ["procured_ai_candidate"],
                "provenance":   provenance,
                "confidence":   0.3,
                "evidence":     {**evidence, "match_type": "ai_keyword", "matched_keyword": kw},
            })
            continue

        # Recognised by nothing. Keep it (opt-in) as signature-authoring material rather
        # than only incrementing a counter — see collect_unmatched above.
        if collect_unmatched and len(unmatched) < MAX_UNMATCHED_REPORTED:
            rec = {k: row[k] for k in collect_unmatched if row.get(k) not in (None, "")}
            if rec:
                unmatched.append(rec)
        skipped += 1

    matched    = sum(1 for a in assets if a["asset_types"] == ["procured_ai"])
    candidates_n = sum(1 for a in assets if a["asset_types"] == ["procured_ai_candidate"])
    out = {
        "assets": assets,
        "skipped": skipped,
        "source_meta": {"rows": len(rows), "matched": matched, "candidates": candidates_n},
    }
    if collect_unmatched:
        out["unmatched"] = unmatched
        # Say so explicitly. A silently truncated list would have us conclude a tenant
        # only had 200 unknown apps when it had 900.
        out["unmatched_truncated"] = skipped > len(unmatched)
    return out
