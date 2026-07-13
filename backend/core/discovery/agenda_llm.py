"""
agenda_llm.py — provider-agnostic agenda ITEM extractor (I/O layer, core/ not engine/).

Turns gated agenda items ("RFP No. 2026-110 — Award AI permitting assistant to
Tyler Technologies for $120,000") into {vendor, product, amount}, which the shared
matcher then judges. This is the ONLY agenda component that may call an LLM, so it
lives in core/ (the engine stays storage-agnostic and dependency-free).

Single swap point via config.AGENDA_LLM_PROVIDER:
  keyword — NO LLM (zero-dep default): use the item title as the product text so
            the AI-keyword screen still surfaces AI-named award items for review.
  vertex  — Gemini on Vertex AI: structured JSON extraction, low temperature,
            reuses the GCP service account (enterprise no-train), item text only.
            Lazy-imported; degrades to keyword on any error (fail-open to review,
            never crashes the run).
  none    — disabled (returns []).

SCALE: the vertex path BATCHES one call per MEETING (not per item) and runs those
per-meeting calls on a BOUNDED thread pool (config.AGENDA_LLM_CONCURRENCY). A wide
12-month window that was ~M sequential calls (one per item) becomes ~K/concurrency
(K = meetings), which keeps the whole run under the Cloud Run request timeout.

Governance / dogfooding: the vertex path stamps {_llm_model} on each item so the
extraction step is itself documented in the audit trail. Every returned item also
carries {_extractor} ('vertex' or 'keyword') so the orchestrator can report which
extractor ACTUALLY ran — including the silent per-meeting fail-open to keyword.
See docs/AGENDA_ENGINE_DESIGN.md.
"""
from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Tuple

# JSON schema the LLM must return: an array with one object per numbered item.
_BATCH_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "index":   {"type": "integer"},
            "vendor":  {"type": "string"},
            "product": {"type": "string"},
            "amount":  {"type": "string"},
            "action":  {"type": "string"},
        },
    },
}

_SYSTEM_BATCH = (
    "You extract procurement facts from U.S. municipal council agenda items. You "
    "are given a NUMBERED list of items. Return a JSON array; for EACH item return "
    "an object with its 1-based `index` and the awarded vendor company, the "
    "product/service, the dollar amount (as written, else empty), and the action "
    "(awarded/renewed/discussed). Include every index exactly once. Do not infer or "
    "invent a vendor. If none is stated, return empty strings."
)


def _keyword_item(it: Dict[str, Any]) -> Dict[str, Any]:
    """One item, no-LLM: title becomes the product so the AI-keyword screen fires."""
    return {
        **it,
        "vendor":  it.get("vendor", ""),
        "product": it.get("product") or it.get("item_title") or it.get("text", ""),
        "amount":  it.get("amount", ""),
        "_extractor": "keyword",   # provenance: no-LLM screen produced this item
    }


def _keyword_extract(items: List[Dict[str, Any]], city: str) -> List[Dict[str, Any]]:
    """No-LLM fallback for a whole list (the 'keyword' provider, or vertex init failure)."""
    return [_keyword_item(it) for it in items]


# ── pure helpers (unit-testable without Vertex) ───────────────────────────────

def _group_key(it: Dict[str, Any]) -> Tuple[str, str, str]:
    """Items from the same meeting share date + type + agenda URL."""
    return (it.get("meeting_date", ""), it.get("meeting_type", ""), it.get("source_url", ""))


def _group_by_meeting(items: List[Dict[str, Any]]) -> List[List[Tuple[int, Dict[str, Any]]]]:
    """Group items by meeting, preserving first-seen order and each item's original
    index so results can be re-assembled in the original order after concurrent runs."""
    groups: "OrderedDict[Tuple[str, str, str], List[Tuple[int, Dict[str, Any]]]]" = OrderedDict()
    for idx, it in enumerate(items):
        groups.setdefault(_group_key(it), []).append((idx, it))
    return list(groups.values())


def _map_meeting_response(group: List[Tuple[int, Dict[str, Any]]],
                          data_array: Any, model: str) -> List[Tuple[int, Dict[str, Any]]]:
    """Map a meeting's LLM array back onto its items by 1-based `index`. Any item the
    model omitted (or a malformed row) falls back to the keyword item — so a partial
    LLM response never drops an item, it just marks that one as keyword-derived."""
    by_index: Dict[int, Dict[str, Any]] = {}
    if isinstance(data_array, list):
        for d in data_array:
            if not isinstance(d, dict):
                continue
            try:
                by_index[int(d.get("index"))] = d
            except (TypeError, ValueError):
                continue
    out: List[Tuple[int, Dict[str, Any]]] = []
    for pos, (orig_idx, it) in enumerate(group, start=1):
        d = by_index.get(pos)
        if d is None:
            out.append((orig_idx, {**_keyword_item(it), "_llm_model": model}))
        else:
            out.append((orig_idx, {
                **it,
                "vendor":    (d.get("vendor") or "").strip(),
                "product":   (d.get("product") or it.get("item_title") or "").strip(),
                "amount":    (d.get("amount") or it.get("amount") or "").strip(),
                "action":    (d.get("action") or it.get("action") or "").strip(),
                "_llm_model": model,
                "_extractor": "vertex",
            }))
    return out


def _vertex_extractor(model: str, project: str, location: str) -> Callable:
    def _fn(items: List[Dict[str, Any]], city: str) -> List[Dict[str, Any]]:
        # TODO: enforce system-level invocation only (auth placeholder).
        if not items:
            return []
        try:
            from google import genai                       # google-genai SDK
            from google.genai import types
            client = genai.Client(vertexai=True, project=project, location=location)
        except Exception as exc:
            print(f"[agenda_llm] vertex unavailable ({type(exc).__name__}) — using keyword fallback")
            return _keyword_extract(items, city)

        def _extract_group(group: List[Tuple[int, Dict[str, Any]]]) -> List[Tuple[int, Dict[str, Any]]]:
            lines = []
            for pos, (_, it) in enumerate(group, start=1):
                txt = (it.get("text") or it.get("item_title") or "").replace("\n", " ").strip()
                lines.append(f"{pos}. {txt}")
            prompt = f"{_SYSTEM_BATCH}\n\nAGENDA ITEMS:\n" + "\n".join(lines)
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        response_schema=_BATCH_SCHEMA,
                    ),
                )
                data = json.loads(resp.text or "[]")
            except Exception as exc:
                print(f"[agenda_llm] batch extract error, keyword-fallback for "
                      f"{len(group)} item(s): {exc}")
                return [(oi, {**_keyword_item(it), "_llm_model": model}) for oi, it in group]
            return _map_meeting_response(group, data, model)

        groups = _group_by_meeting(items)
        from core import config
        workers = max(1, min(int(getattr(config, "AGENDA_LLM_CONCURRENCY", 6)), len(groups)))

        if workers <= 1 or len(groups) == 1:
            mapped = [_extract_group(g) for g in groups]
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as ex:
                mapped = list(ex.map(_extract_group, groups))

        # Re-assemble in the original item order.
        out: List[Dict[str, Any]] = [None] * len(items)  # type: ignore[list-item]
        for grp in mapped:
            for orig_idx, enriched in grp:
                out[orig_idx] = enriched
        # Safety net: any slot left unfilled (should not happen) → keyword.
        return [o if o is not None else _keyword_item(items[i]) for i, o in enumerate(out)]

    return _fn


def get_extractor(provider: str = None, model: str = None) -> Callable[[List[Dict[str, Any]], str], List[Dict[str, Any]]]:
    """Return the configured extract_fn (single swap point). `provider` and `model`
    override the config defaults (so the admin Settings toggles take effect at
    runtime without a redeploy)."""
    from core import config
    provider = provider or getattr(config, "AGENDA_LLM_PROVIDER", "keyword")
    if provider in ("none", ""):
        return lambda items, city: []
    if provider in ("vertex", "gemini"):
        return _vertex_extractor(
            model or getattr(config, "AGENDA_LLM_MODEL", "gemini-2.5-flash-lite"),
            getattr(config, "FIRESTORE_PROJECT_ID", ""),
            getattr(config, "AGENDA_LLM_LOCATION", "us-central1"),
        )
    return _keyword_extract
