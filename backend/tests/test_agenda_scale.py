"""
test_agenda_scale.py — concurrency + per-meeting LLM batching (no network, no LLM).

Covers the scale fix for wide date windows (12-month backfills that were 502-ing on
Cloud Run's 300s request timeout):
  - fetch_legistar fetches per-meeting item lists on a bounded pool, order-preserving.
  - the vertex extractor groups items by meeting and maps one array response back by
    index, with per-item keyword fail-open on a partial/malformed response.
These are the pure/injectable seams; the live Vertex call itself is not exercised here.
"""
from core.discovery import agenda_llm as L
from core.discovery import agenda_fetch as F


# ── per-meeting grouping + response mapping (pure) ────────────────────────────

_ITEMS = [
    {"item_title": "Award A", "meeting_date": "2026-01-05", "meeting_type": "City Council", "source_url": "u1"},
    {"item_title": "Award B", "meeting_date": "2026-01-05", "meeting_type": "City Council", "source_url": "u1"},
    {"item_title": "Award C", "meeting_date": "2026-02-02", "meeting_type": "City Council", "source_url": "u2"},
]


def test_group_by_meeting_preserves_indices():
    groups = L._group_by_meeting(_ITEMS)
    assert [len(g) for g in groups] == [2, 1]
    assert groups[0][0][0] == 0 and groups[0][1][0] == 1 and groups[1][0][0] == 2


def test_full_response_maps_all_vertex():
    g0 = L._group_by_meeting(_ITEMS)[0]
    resp = [{"index": 1, "vendor": "Citibot", "product": "chatbot"},
            {"index": 2, "vendor": "Tyler", "product": "permitting AI"}]
    mapped = L._map_meeting_response(g0, resp, "gemini-x")
    assert [e["_extractor"] for _, e in mapped] == ["vertex", "vertex"]
    assert mapped[0][1]["vendor"] == "Citibot" and mapped[1][1]["vendor"] == "Tyler"


def test_partial_response_falls_back_per_item():
    g0 = L._group_by_meeting(_ITEMS)[0]
    mapped = L._map_meeting_response(g0, [{"index": 1, "vendor": "Citibot"}], "gemini-x")
    assert [e["_extractor"] for _, e in mapped] == ["vertex", "keyword"]
    # keyword-fallback item keeps its title as product so the AI-keyword screen still fires
    assert mapped[1][1]["product"] == "Award B"


def test_malformed_response_all_keyword():
    g0 = L._group_by_meeting(_ITEMS)[0]
    mapped = L._map_meeting_response(g0, "not-a-list", "gemini-x")
    assert all(e["_extractor"] == "keyword" for _, e in mapped)


# ── parallel Legistar fetch (injected fetch_json; order preserved) ────────────

def _fake_portal(url):
    if "/eventitems" in url:   # items endpoint: .../events/{id}/eventitems
        eid = int(url.split("/events/")[1].split("/")[0])
        return [{"EventItemTitle": f"Award contract to Vendor{eid}", "EventItemMatterFile": f"F{eid}"}]
    # events list (may carry a ?$filter=... query for the date window)
    return [{"EventId": 100 + i, "EventBodyName": "City Council",
             "EventDate": f"2026-01-0{i + 1}T00:00:00", "EventInSiteURL": f"http://a/{100 + i}"}
            for i in range(5)]


def test_parallel_fetch_returns_all_items_in_order():
    got = F.fetch_legistar("cityoflewisville", since="2026-01-01", until="2026-01-31",
                           fetch_json=_fake_portal)
    assert len(got) == 5
    assert [g["file_number"] for g in got] == ["F100", "F101", "F102", "F103", "F104"]


def test_events_url_is_date_filtered():
    # Regression: a long-standing Legistar tenant (McKinney, events since 2009) returns
    # its OLDEST ~1000 events by default. Without a server-side date filter the recent
    # window is never returned and the scan finds nothing. fetch_legistar must filter.
    seen = {}
    def _capture(url):
        seen["events" if "/eventitems" not in url else "items"] = url
        return _fake_portal(url)
    F.fetch_legistar("mckinney", since="2025-07-13", until="2026-07-13", fetch_json=_capture)
    assert "$filter=" in seen["events"] and "EventDate" in seen["events"], seen["events"]


def test_empty_meeting_list_is_safe():
    got = F.fetch_legistar("x", since="2099-01-01", until="2099-01-02", fetch_json=_fake_portal)
    assert got == []
