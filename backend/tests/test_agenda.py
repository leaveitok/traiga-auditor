"""
test_agenda.py — pure council-agenda discovery core.

Verifies (no network, no LLM): platform fingerprinting, the award/procurement
keyword gate, item segmentation, and normalize() turning LLM-extracted items into
discovered_agenda assets via the SHARED procurement matcher — with provenance
overridden and agenda evidence carried through.
"""
from engine.collectors import agenda, identity

SCHEMA = {
    "AI_Tool_Catalog": {
        "ai_keywords": ["ai", "artificial intelligence", "machine learning", "chatbot", "copilot"],
        "tools": [
            {"tool_id": "openai_chatgpt", "display_name": "ChatGPT (OpenAI)",
             "aliases": {"procurement_names": ["openai", "chatgpt"]}},
            {"tool_id": "microsoft_copilot", "display_name": "Microsoft Copilot",
             "aliases": {"procurement_names": ["microsoft copilot"], "product_names": ["copilot"]}},
        ],
    },
    "AI_Vendor_Fingerprints": {"vendors": []},
}
INDEX = identity.build_tool_index(SCHEMA)


def test_platform_fingerprint():
    assert agenda.fingerprint_platform("https://lewisville.legistar.com/Calendar.aspx") == "legistar"
    assert agenda.fingerprint_platform("https://denton.civicweb.net/portal") == "civicplus"
    assert agenda.fingerprint_platform("https://agenda.friscotexas.gov/OnBaseAgendaOnline/") == "onbase"
    # iCompass embedded on the city's own domain — detected via page HTML, not URL.
    assert agenda.fingerprint_platform(
        "https://plano.gov/city-council-agendas",
        html='<iframe src="https://plano.iqm2.com/Citizens/"></iframe>') == "diligent"
    assert agenda.fingerprint_platform("https://randomcity.gov/agenda") is None


def test_meeting_type_filter():
    for t in ("City Council Regular Meeting", "Economic Development Corporation",
              "Community Development Corporation"):
        assert agenda.is_relevant_meeting(t) is True
    for t in ("Planning and Zoning Commission", "Zoning Board of Adjustment",
              "Board of Adjustment", "Parks Advisory Board"):
        assert agenda.is_relevant_meeting(t) is False


def test_procurement_gate():
    assert agenda.is_procurement_item("Consideration to AWARD a contract to OpenAI")
    assert not agenda.is_procurement_item("Proclamation recognizing Fire Prevention Week")


def test_segmentation():
    seg = agenda.segment_items("1. Award contract to OpenAI.\n2. Approve minutes.\n3. Adjourn.")
    assert len(seg) == 3 and seg[0]["title"].startswith("1.")


def test_normalize_agenda_items():
    items = [
        {"vendor": "OpenAI", "product": "ChatGPT Enterprise", "action": "awarded",
         "amount": "$48,000", "meeting_date": "2026-06-03", "item_title": "Award AI contract",
         "source_url": "https://x/legistar/item/1"},
        {"vendor": "Tyler Technologies", "product": "AI permitting assistant", "action": "awarded",
         "meeting_date": "2026-06-03", "source_url": "https://x/item/2"},
        {"vendor": "Acme Paving", "product": "street resurfacing", "action": "awarded"},
    ]
    res = agenda.normalize(items, INDEX, "City of Lewisville")
    tools = {a["tool_id"] for a in res["assets"]}
    assert "openai_chatgpt" in tools
    assert any(a["asset_types"] == ["procured_ai_candidate"] for a in res["assets"])  # Tyler
    assert res["skipped"] == 1  # Acme Paving

    oa = next(a for a in res["assets"] if a["tool_id"] == "openai_chatgpt")
    assert oa["provenance"] == "discovered_agenda"
    assert oa["evidence"]["meeting_date"] == "2026-06-03"
    assert oa["evidence"]["action"] == "awarded"
    assert oa["evidence"]["source_url"].endswith("/item/1")


def test_legistar_parser():
    from engine.collectors import agenda_legistar as L
    events = [
        {"EventId": 101, "EventBodyName": "City Council", "EventDate": "2026-06-03T00:00:00",
         "EventInSiteURL": "https://x.legistar.com/MeetingDetail.aspx?ID=101"},
        {"EventId": 102, "EventBodyName": "Planning and Zoning Commission", "EventDate": "2026-06-10T00:00:00"},
        {"EventId": 103, "EventBodyName": "City Council", "EventDate": "2024-01-01T00:00:00"},  # too old
    ]
    evs = L.parse_events(events, since="2026-01-01", until="2026-12-31")
    ids = {e["event_id"] for e in evs}
    assert ids == {101}  # P&Z filtered, old date filtered
    assert next(e for e in evs if e["event_id"] == 101)["meeting_date"] == "2026-06-03"

    meeting = evs[0]
    items = [
        {"EventItemTitle": "RFP No. 2026-110 - Award AI permitting assistant to Tyler Technologies",
         "EventItemActionText": "Approved", "EventItemMatterFile": "26-6231"},
        {"EventItemTitle": "Proclamation recognizing Fire Prevention Week"},
    ]
    parsed = L.parse_event_items(items, meeting)
    assert len(parsed) == 1  # proclamation dropped by the award gate
    assert parsed[0]["file_number"] == "26-6231"
    assert parsed[0]["meeting_date"] == "2026-06-03"
    assert parsed[0]["source_url"].endswith("ID=101")
    assert L.event_endpoints("cityoflewisville")["events"].endswith("/cityoflewisville/events")


def test_fetch_legistar_with_fake_http():
    """fetch_legistar chains events→items with an INJECTED fetch_json (no live HTTP)."""
    from core.discovery.agenda_fetch import fetch_legistar
    events = [
        {"EventId": 101, "EventBodyName": "City Council", "EventDate": "2026-06-03T00:00:00",
         "EventInSiteURL": "https://x.legistar.com/MeetingDetail.aspx?ID=101"},
        {"EventId": 102, "EventBodyName": "Planning and Zoning Commission", "EventDate": "2026-06-10T00:00:00"},
    ]
    items = {101: [
        {"EventItemTitle": "RFP 2026-110 - Award AI permitting assistant to Tyler Technologies",
         "EventItemActionText": "Approved", "EventItemMatterFile": "26-6231"},
        {"EventItemTitle": "Proclamation - Fire Prevention Week"},
    ]}

    def fake(url):
        if "/eventitems" in url:
            import re
            return items.get(int(re.search(r"/events/(\d+)/", url).group(1)), [])
        return events   # events list (may carry a ?$filter=... date query)

    parsed = fetch_legistar("cityoftest", since="2026-01-01", until="2026-12-31", fetch_json=fake)
    # P&Z meeting skipped; proclamation gated out; one award item remains.
    assert len(parsed) == 1
    assert parsed[0]["meeting_type"] == "City Council"
    assert parsed[0]["file_number"] == "26-6231"
    assert parsed[0]["source_url"].endswith("ID=101")
