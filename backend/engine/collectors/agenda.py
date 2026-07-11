"""
agenda.py — council-agenda discovery: PURE parsing + normalization (no I/O, no LLM).

The pipeline's pure stages live here so they unit-test without network or an LLM
(fetch + LLM extraction are in core/discovery/agenda_source.py):
  fingerprint_platform — which agenda system (Legistar/Granicus, CivicPlus, ...)
  segment_items        — split an agenda into individual items
  is_procurement_item  — keyword gate to award/contract items (bounds LLM spend)
  normalize            — turn LLM-EXTRACTED items into discovered_agenda assets
                         via the SHARED procurement matcher (provenance override)

An agenda contract-award item is a {vendor, product, amount} row; everything
downstream of that already exists (identity resolver, catalog, AI-keyword screen,
merge). See docs/AGENDA_ENGINE_DESIGN.md.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.collectors import procurement

PROVENANCE = "discovered_agenda"

# ── Agenda-platform fingerprints (pick the parser, like website vendors) ──────
_PLATFORMS = [
    ("legistar",    [r"legistar\.com", r"\.granicus\.com", r"granicus", r"insite"]),
    ("onbase",      [r"onbaseagendaonline", r"onbase\s*agenda"]),          # Frisco et al.
    ("civicplus",   [r"civicplus\.com", r"civicweb\.net"]),
    ("civicclerk",  [r"civicclerk\.com"]),
    ("primegov",    [r"primegov\.com"]),
    # iCompass/Diligent is often EMBEDDED on the city's own domain (e.g. Plano) —
    # detect it in the page HTML (iframe src / script markers), not just the URL.
    ("diligent",    [r"iqm2\.com", r"diligent\.com", r"icompass"]),
    ("escribe",     [r"escribemeetings\.com", r"pub-\w+\.escribe"]),
    ("novusagenda", [r"novusagenda\.com"]),
    ("boarddocs",   [r"boarddocs\.com"]),
]


def fingerprint_platform(url: str = "", html: str = "") -> Optional[str]:
    """
    Return the agenda platform id from the portal URL and/or page HTML, or None.
    IMPORTANT: pass the rendered HTML too — some cities (e.g. Plano) embed a
    third-party portal (iCompass) on their own .gov domain, so the URL alone
    won't reveal the platform; the iframe/script markers in the HTML will.
    """
    hay = f"{url} {html}".lower()
    for pid, pats in _PLATFORMS:
        if any(re.search(p, hay) for p in pats):
            return pid
    return None


# ── Award / procurement gate (word-boundary matched to avoid over-triggering) ─
AWARD_KEYWORDS = [
    "award", "awarded", "contract", "agreement", "purchase", "procure",
    "procurement", "professional services", "sole source", "interlocal",
    "rfp", "rfq", "bid", "renew", "renewal", "amendment", "task order",
    "master services", "subscription", "license",
]


def is_procurement_item(text: str) -> bool:
    """True if the item text looks like a contract/purchase/award action."""
    hay = (text or "").lower()
    return any(re.search(r"\b" + re.escape(k) + r"\b", hay) for k in AWARD_KEYWORDS)


# Meeting bodies that AWARD procurement contracts (target) vs. land-use / advisory
# bodies that do NOT (skip — saves LLM budget + avoids noise). Filter at the
# meeting-list stage using the portal's "Meeting Type" column, BEFORE any LLM call.
_SKIP_MEETING_KEYWORDS = (
    "planning", "zoning", "board of adjustment", "advisory", "parks",
    "library", "arts", "historic", "ethics", "appeals", "landmark",
)
_TARGET_MEETING_KEYWORDS = (
    "council", "commissioners court", "economic development",
    "community development", "edc", "cdc",
)


def is_relevant_meeting(meeting_type: str) -> bool:
    """
    Should this meeting's agenda be scanned for procured AI?
    Contract awards live at City Council and EDC/CDC; Planning & Zoning, Zoning
    Board of Adjustment, and advisory boards do not procure — skip them.
    Unknown types default to True (the item gate + AI match still filter), but
    an explicit land-use/advisory match is skipped to conserve LLM spend.
    """
    t = (meeting_type or "").lower()
    if any(k in t for k in _TARGET_MEETING_KEYWORDS):
        return True
    if any(k in t for k in _SKIP_MEETING_KEYWORDS):
        return False
    return True


# Item numbering at line start: "1.", "12)", "A.", "3.2", "Item 4", "Agenda Item 5"
_ITEM_MARK = re.compile(
    r"^\s*(?:agenda\s+item|item)?\s*(?:\d{1,3}(?:\.\d{1,3})?|[A-Z])\s*[\.\)]\s+",
    re.IGNORECASE | re.MULTILINE)


def segment_items(text: str) -> List[Dict[str, Any]]:
    """
    Heuristic split of agenda plain text into items. Platform-specific parsers
    refine this later; this is the generic fallback. Returns [{title, text}].
    """
    if not text:
        return []
    marks = list(_ITEM_MARK.finditer(text))
    if not marks:
        return [{"title": ln.strip(), "text": ln.strip()}
                for ln in text.splitlines() if ln.strip()]
    items: List[Dict[str, Any]] = []
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[start:end].strip()
        title = chunk.splitlines()[0].strip() if chunk else ""
        items.append({"title": title, "text": chunk})
    return items


def normalize(extracted_items: List[Dict[str, Any]], index: Dict[str, Any],
              city: str, min_confidence: Optional[float] = None) -> Dict[str, Any]:
    """
    extracted_items: LLM-extracted dicts, each
      {vendor, product|service, action, amount, meeting_date, item_title, source_url}.
    Delegates to the SHARED procurement matcher with provenance=discovered_agenda
    and carries agenda evidence through. Returns a DiscoveryResult.
    TODO: enforce system-level invocation only (auth placeholder).
    """
    mc = procurement.DEFAULT_MIN_CONFIDENCE if min_confidence is None else min_confidence
    rows: List[Dict[str, Any]] = []
    for it in (extracted_items or []):
        rows.append({
            "vendor":       (it.get("vendor") or "").strip(),
            "product":      (it.get("product") or it.get("service") or "").strip(),
            "city":         city,
            "amount":       it.get("amount") or it.get("amount_band") or "",
            "contract_id":  it.get("file_number") or it.get("contract_id") or "",
            "meeting_date": it.get("meeting_date", ""),
            "item_title":   it.get("item_title", ""),
            "source_url":   it.get("source_url", ""),
            "action":       it.get("action", ""),
        })
    return procurement.normalize(
        rows, index, city_field="city", min_confidence=mc,
        provenance=PROVENANCE,
        extra_evidence_fields=("meeting_date", "item_title", "source_url", "action"),
    )
