"""
agenda_llm.py — provider-agnostic agenda ITEM extractor (I/O layer, core/ not engine/).

Turns a gated agenda item ("RFP No. 2026-110 — Award AI permitting assistant to
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

Governance / dogfooding: the vertex path stamps {_llm_model} on each item so the
extraction step is itself documented in the audit trail. See docs/AGENDA_ENGINE_DESIGN.md.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

# JSON schema the LLM must return per item (structured output).
_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor":  {"type": "string"},
        "product": {"type": "string"},
        "amount":  {"type": "string"},
        "action":  {"type": "string"},
    },
}

_SYSTEM = (
    "You extract procurement facts from a single U.S. municipal council agenda "
    "item. Return ONLY the awarded vendor company, the product/service, the dollar "
    "amount (as written, else empty), and the action (awarded/renewed/discussed). "
    "Do not infer or invent a vendor. If none is stated, return empty strings."
)


def _keyword_extract(items: List[Dict[str, Any]], city: str) -> List[Dict[str, Any]]:
    """No-LLM fallback: title becomes the product so the AI-keyword screen fires."""
    out: List[Dict[str, Any]] = []
    for it in items:
        out.append({
            **it,
            "vendor":  it.get("vendor", ""),
            "product": it.get("product") or it.get("item_title") or it.get("text", ""),
            "amount":  it.get("amount", ""),
        })
    return out


def _vertex_extractor(model: str, project: str, location: str) -> Callable:
    def _fn(items: List[Dict[str, Any]], city: str) -> List[Dict[str, Any]]:
        # TODO: enforce system-level invocation only (auth placeholder).
        try:
            from google import genai                       # google-genai SDK
            from google.genai import types
            client = genai.Client(vertexai=True, project=project, location=location)
        except Exception as exc:
            print(f"[agenda_llm] vertex unavailable ({type(exc).__name__}) — using keyword fallback")
            return _keyword_extract(items, city)

        out: List[Dict[str, Any]] = []
        for it in items:
            text = it.get("text") or it.get("item_title") or ""
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=f"{_SYSTEM}\n\nAGENDA ITEM:\n{text}",
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        response_schema=_EXTRACTION_SCHEMA,
                    ),
                )
                data = json.loads(resp.text or "{}")
            except Exception as exc:
                print(f"[agenda_llm] extract error, keyword-fallback for one item: {exc}")
                data = {}
            out.append({
                **it,
                "vendor":    (data.get("vendor") or "").strip(),
                "product":   (data.get("product") or it.get("item_title") or "").strip(),
                "amount":    (data.get("amount") or it.get("amount") or "").strip(),
                "action":    (data.get("action") or it.get("action") or "").strip(),
                "_llm_model": model,      # audit-trail: which model produced this
            })
        return out
    return _fn


def get_extractor(provider: str = None) -> Callable[[List[Dict[str, Any]], str], List[Dict[str, Any]]]:
    """Return the configured extract_fn (single swap point). `provider` overrides
    the config default (so the admin Settings toggle takes effect at runtime)."""
    from core import config
    provider = provider or getattr(config, "AGENDA_LLM_PROVIDER", "keyword")
    if provider in ("none", ""):
        return lambda items, city: []
    if provider in ("vertex", "gemini"):
        return _vertex_extractor(
            getattr(config, "AGENDA_LLM_MODEL", "gemini-2.5-flash-lite"),
            getattr(config, "FIRESTORE_PROJECT_ID", ""),
            getattr(config, "AGENDA_LLM_LOCATION", "us-central1"),
        )
    return _keyword_extract
