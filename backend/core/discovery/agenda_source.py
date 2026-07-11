"""
agenda_source.py — council-agenda discovery ORCHESTRATOR (I/O + LLM + merge).

A SEPARATE engine from the website compliance scanner, with ISOLATED execution
(flag-gated by config.AGENDA_ENGINE_ENABLED, off by default). It reuses the
shared substrate: the crawler (fetch), the identity resolver + tool catalog, the
procurement matcher, and the registry merge. It writes DISCOVERY rows only
(`discovered_agenda`) — never disclosure violations or the cure clock.

Extraction is INJECTABLE: `extract_fn(item_texts, city, agenda_url) -> [items]`
lets tests pass a fake extractor and production wire an enterprise (no-train) LLM.
Beta usage: pass pre-extracted `items` (no LLM needed) or a raw `agenda_text`.

See docs/AGENDA_ENGINE_DESIGN.md.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

from engine import rule_loader
from engine.collectors import agenda
from engine.collectors.identity import build_tool_index
from core.discovery.merge import merge_discovered_assets

PROVENANCE = agenda.PROVENANCE


def _disabled_result() -> Dict[str, Any]:
    return {"written": 0, "matched": 0, "candidates": 0, "skipped": 0,
            "rows": 0, "cities": [], "errors": ["agenda_engine_disabled"]}


def run_agenda_discovery(
    repo: Any,
    city: str,
    *,
    items: Optional[List[Dict[str, Any]]] = None,          # pre-extracted (vendor/product present)
    parsed_items: Optional[List[Dict[str, Any]]] = None,   # gated items, need LLM enrichment
    agenda_text: Optional[str] = None,                     # raw agenda text (segment + gate here)
    agenda_url: str = "",
    extract_fn: Optional[Callable[[List[Dict[str, Any]], str], List[Dict[str, Any]]]] = None,
    min_confidence: Optional[float] = None,
    allowed_cities: Optional[Set[str]] = None,
    actor: str = "system",
) -> Dict[str, Any]:
    """
    Discover AI from council-agenda contract-award items and merge into ai_assets.
    Returns {written, matched, candidates, skipped, rows, cities, errors}.

    TODO: enforce system/admin-only invocation (auth placeholder — route enforces).
    """
    from core import settings
    if not settings.get_bool(repo, "AGENDA_ENGINE_ENABLED"):
        return _disabled_result()

    # Fail-secure tenancy: an agency user can only write assets for its own cities.
    if allowed_cities is not None and city not in allowed_cities:
        return {**_disabled_result(), "errors": ["city_out_of_scope"]}

    schema = rule_loader.load_schema()
    index = build_tool_index(schema)

    # Resolve the extractor (single swap point: config.AGENDA_LLM_PROVIDER),
    # injectable for tests. extract_fn(items, city) -> items enriched with vendor/product.
    from core.discovery.agenda_llm import get_extractor
    from core import settings as _settings
    extractor = extract_fn or get_extractor(_settings.get_value(repo, "AGENDA_LLM_PROVIDER"))

    if items is not None:
        # Already extracted (vendor/product present) — beta / manual / test path.
        extracted = items
    elif parsed_items is not None:
        # Gated portal items (title + evidence) — enrich with the LLM/keyword extractor.
        extracted = extractor(parsed_items, city) or []
    elif agenda_text:
        # Raw agenda text — segment + award-gate here, then enrich.
        segs = agenda.segment_items(agenda_text)
        cands = [{"text": s.get("text", ""), "item_title": s.get("title", ""),
                  "source_url": agenda_url}
                 for s in segs if agenda.is_procurement_item(s.get("text", ""))]
        extracted = extractor(cands, city) or [] if cands else []
    else:
        extracted = []   # nothing supplied -> no-op (fail-secure)

    result = agenda.normalize(extracted, index, city, min_confidence=min_confidence)
    merged = merge_discovered_assets(repo, result)

    try:
        repo.append_audit_log(
            event="discovery_agenda",
            city_count=len(merged["cities"]),
            failures=result["skipped"],
            details={
                "actor":   actor,
                "summary": f"Agenda discovery for {city}: {merged['written']} AI items merged "
                           f"({result['source_meta']['candidates']} for review)",
                "agenda_url": agenda_url,
                "matched":    result["source_meta"]["matched"],
                "candidates": result["source_meta"]["candidates"],
            },
        )
    except Exception as exc:
        print(f"[discovery] WARN: could not log agenda run: {exc}")

    return {
        **merged,
        "matched":    result["source_meta"]["matched"],
        "candidates": result["source_meta"]["candidates"],
        "rows":       result["source_meta"]["rows"],
    }


def run_legistar_discovery(
    repo: Any,
    city: str,
    legistar_client: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    fetch_json: Optional[Callable[[str], Any]] = None,   # injectable for tests
    extract_fn: Optional[Callable[[List[Dict[str, Any]], str], List[Dict[str, Any]]]] = None,
    min_confidence: Optional[float] = None,
    allowed_cities: Optional[Set[str]] = None,
    actor: str = "system",
) -> Dict[str, Any]:
    """
    End-to-end Legistar path: fetch gated agenda items over the date window, then
    enrich + normalize + merge via run_agenda_discovery. Flag-gated + tenancy-guarded
    there. `fetch_json` is injectable so this is testable without live HTTP.
    """
    from core import settings
    if not settings.get_bool(repo, "AGENDA_ENGINE_ENABLED"):
        return _disabled_result()

    from core.discovery.agenda_fetch import fetch_legistar
    try:
        parsed = fetch_legistar(legistar_client, since=since, until=until, fetch_json=fetch_json)
    except Exception as exc:
        print(f"[discovery] agenda fetch failed for {city}/{legistar_client}: {exc}")
        return {**_disabled_result(), "errors": [f"fetch_failed:{type(exc).__name__}"]}

    return run_agenda_discovery(
        repo, city, parsed_items=parsed, agenda_url=f"legistar:{legistar_client}",
        extract_fn=extract_fn, min_confidence=min_confidence,
        allowed_cities=allowed_cities, actor=actor,
    )


def run_pdf_discovery(
    repo: Any,
    city: str,
    pdf_url: str,
    *,
    meeting: Optional[Dict[str, Any]] = None,
    fetch_bytes: Optional[Callable[[str], bytes]] = None,   # injectable for tests
    extract_fn: Optional[Callable[[List[Dict[str, Any]], str], List[Dict[str, Any]]]] = None,
    min_confidence: Optional[float] = None,
    allowed_cities: Optional[Set[str]] = None,
    actor: str = "system",
) -> Dict[str, Any]:
    """
    PDF agenda path (portals without an API): download → pdfminer text → gated
    items → enrich + normalize + merge. Flag-gated + tenancy-guarded downstream.
    fetch_bytes is injectable so this is testable without live HTTP.
    """
    from core import settings
    if not settings.get_bool(repo, "AGENDA_ENGINE_ENABLED"):
        return _disabled_result()

    from core.discovery.agenda_fetch import fetch_pdf_agenda
    try:
        parsed = fetch_pdf_agenda(pdf_url, meeting=meeting, fetch_bytes=fetch_bytes)
    except Exception as exc:
        print(f"[discovery] agenda PDF fetch failed for {city}/{pdf_url}: {exc}")
        return {**_disabled_result(), "errors": [f"pdf_fetch_failed:{type(exc).__name__}"]}

    return run_agenda_discovery(
        repo, city, parsed_items=parsed, agenda_url=pdf_url,
        extract_fn=extract_fn, min_confidence=min_confidence,
        allowed_cities=allowed_cities, actor=actor,
    )
