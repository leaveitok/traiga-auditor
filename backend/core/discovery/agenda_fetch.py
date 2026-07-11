"""
agenda_fetch.py — fetch agenda data from portals (I/O layer, core/ not engine/).

`fetch_json` is INJECTABLE so unit tests pass fixtures (no live HTTP, no creds).
Legistar first (structured Web API JSON). OnBase (HTML + PDF via pdfminer) and the
other platforms are follow-ups that produce the same flat item-dict shape.
See docs/AGENDA_ENGINE_DESIGN.md.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from engine.collectors import agenda_legistar as legistar


def _default_fetch_json(url: str) -> Any:
    # Demand-driven proxy could be added here (AGENDA_PROXY_URL) when a portal
    # blocks datacenter IPs — the agenda portal is usually a different host than
    # the city website, so proxy use is decided per-portal, not by the WAF flag.
    import requests
    r = requests.get(url, timeout=30, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def fetch_legistar(client: str, since: Optional[str] = None, until: Optional[str] = None,
                   fetch_json: Optional[Callable[[str], Any]] = None,
                   max_events: int = 200) -> List[Dict[str, Any]]:
    """
    Return a flat list of gated agenda item dicts for a Legistar client
    (e.g. "cityoflewisville"). Applies the date window + meeting-type + award gates
    (in the parser) so only relevant items are fetched deeply.
    TODO: enforce system-level invocation only (auth placeholder).
    """
    fj = fetch_json or _default_fetch_json
    eps = legistar.event_endpoints(client)
    events_raw = fj(eps["events"]) or []
    meetings = legistar.parse_events(events_raw, since=since, until=until)[:max_events]

    items: List[Dict[str, Any]] = []
    for m in meetings:
        try:
            raw = fj(eps["event_items"].format(event_id=m["event_id"])) or []
        except Exception as exc:
            print(f"[agenda_fetch] items fetch failed for event {m.get('event_id')}: {exc}")
            continue
        items.extend(legistar.parse_event_items(raw, m))
    return items


# ── PDF agenda path (portals without a clean API: OnBase, CivicPlus PDFs, ...) ─

def pdf_bytes_to_text(data: bytes, max_pages: int = 80, max_chars: int = 2_000_000) -> str:
    """Extract text from a PDF (pdfminer, lazy). Page/char caps bound cost — some
    agenda packets are large (a Frisco packet was 16 MB). Returns '' on failure."""
    from io import BytesIO
    try:
        from pdfminer.high_level import extract_text
    except Exception as exc:
        print(f"[agenda_fetch] pdfminer unavailable: {exc}")
        return ""
    try:
        text = extract_text(BytesIO(data), maxpages=max_pages) or ""
    except Exception as exc:
        print(f"[agenda_fetch] PDF parse failed: {exc}")
        return ""
    return text[:max_chars]


def parse_pdf_agenda(text: str, meeting: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    PURE: agenda PDF text → gated item dicts. Segment (coarse — PDF numbering is
    noisy, the extractor does the heavy lifting) + award gate. Testable with plain text.
    """
    from engine.collectors import agenda
    m = meeting or {}
    items: List[Dict[str, Any]] = []
    for seg in agenda.segment_items(text):
        if not agenda.is_procurement_item(seg.get("text", "")):
            continue
        items.append({
            "text":         seg.get("text", "")[:2000],
            "item_title":   seg.get("title", ""),
            "meeting_date": m.get("meeting_date", ""),
            "meeting_type": m.get("meeting_type", ""),
            "source_url":   m.get("source_url") or m.get("agenda_url", ""),
        })
    return items


def _default_fetch_bytes(url: str) -> bytes:
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def fetch_pdf_agenda(pdf_url: str, meeting: Optional[Dict[str, Any]] = None,
                     fetch_bytes: Optional[Callable[[str], bytes]] = None) -> List[Dict[str, Any]]:
    """I/O: download a PDF agenda → text → gated items. fetch_bytes injectable for tests."""
    fb = fetch_bytes or _default_fetch_bytes
    data = fb(pdf_url)
    text = pdf_bytes_to_text(data)
    m = dict(meeting or {})
    m.setdefault("source_url", pdf_url)
    return parse_pdf_agenda(text, m)
