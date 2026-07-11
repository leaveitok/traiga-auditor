"""
agenda_legistar.py — Legistar (Granicus) parser: PURE, no HTTP, no LLM.

Legistar exposes a structured Web API — webapi.legistar.com/v1/{client}/events
and .../events/{id}/eventitems — so items arrive as FIELDS (no HTML scraping and
no LLM needed for segmentation). The orchestrator fetches the JSON; this module
turns it into normalized, gated, dated meeting + item records. Fully testable
with fixtures.

Gates applied HERE (cheapest stage, before any LLM extraction):
  - date range  (since / until, from the lookback window)
  - meeting type (agenda.is_relevant_meeting — council/EDC, not zoning/advisory)
  - award gate   (agenda.is_procurement_item — contract/bid/RFP items only)

Item titles then feed the LLM extractor for {vendor, product, amount}, or the
agenda.normalize matcher directly. See docs/AGENDA_ENGINE_DESIGN.md.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.collectors import agenda

API_BASE = "https://webapi.legistar.com/v1"


def event_endpoints(client: str) -> Dict[str, str]:
    """Legistar Web API endpoints for a client (the orchestrator does the fetch)."""
    c = str(client).strip().strip("/")
    return {
        "events": f"{API_BASE}/{c}/events",
        "event_items": f"{API_BASE}/{c}/events/{{event_id}}/eventitems",
    }


def _date(s: Any) -> str:
    """Legistar EventDate 'YYYY-MM-DDT00:00:00' → 'YYYY-MM-DD' (safe)."""
    t = str(s or "")
    return t[:10] if len(t) >= 10 and t[4] == "-" else ""


def parse_events(events: List[Dict[str, Any]], since: Optional[str] = None,
                 until: Optional[str] = None, relevant_only: bool = True) -> List[Dict[str, Any]]:
    """
    Legistar /events JSON → [{event_id, meeting_type, meeting_date, agenda_url}].
    Applies the date-range window and (optionally) the meeting-type filter.
    """
    out: List[Dict[str, Any]] = []
    for e in (events or []):
        mtype = (e.get("EventBodyName") or "").strip()
        mdate = _date(e.get("EventDate"))
        if since and mdate and mdate < since:
            continue
        if until and mdate and mdate > until:
            continue
        if relevant_only and mtype and not agenda.is_relevant_meeting(mtype):
            continue
        out.append({
            "event_id":     e.get("EventId"),
            "meeting_type": mtype,
            "meeting_date": mdate,
            "agenda_url":   (e.get("EventInSiteURL") or e.get("EventAgendaFile") or "").strip(),
        })
    return out


def parse_event_items(items: List[Dict[str, Any]], meeting: Dict[str, Any],
                      award_only: bool = True) -> List[Dict[str, Any]]:
    """
    Legistar /eventitems JSON → item dicts ready for extraction/normalize.
    `meeting` is one element from parse_events. Keeps only award/contract items
    (award gate) unless award_only=False.
    """
    out: List[Dict[str, Any]] = []
    for it in (items or []):
        title = (it.get("EventItemTitle") or it.get("EventItemMatterName") or "").strip()
        if not title:
            continue
        if award_only and not agenda.is_procurement_item(title):
            continue
        out.append({
            "item_title":   title,
            "text":         title,
            "action":       (it.get("EventItemActionText")
                             or it.get("EventItemPassedFlagName") or "").strip(),
            "file_number":  (it.get("EventItemMatterFile") or "").strip(),
            "meeting_date": meeting.get("meeting_date", ""),
            "meeting_type": meeting.get("meeting_type", ""),
            "source_url":   meeting.get("agenda_url", ""),
        })
    return out
