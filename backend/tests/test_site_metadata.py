"""
test_site_metadata.py — site-metadata detection + persistence (no network, no LLM).

Covers the auto-capture feature that stops the operator re-typing the Legistar slug:
  - the PURE detector reads agenda platform/slug/url, CMS, and privacy URL from the
    observable surface a scan already captures, honoring the slug stoplist;
  - the Mock repo round-trips the metadata fields and site_metadata_verified.
The live crawl + Firestore writes are exercised by CI's route/repo tests.
"""
import json
import os

from engine.collectors.site_metadata import detect_site_metadata
from tests.mock_repository import MockGovernanceRepository

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "SCHEMA_DEFINITION.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    SCHEMA = json.load(_f)


def test_detect_legistar_wordpress_privacy():
    pages = [{
        "url": "https://www.cityoflewisville.com",
        "html": '<link href="/wp-content/x.css">'
                '<a href="https://cityoflewisville.legistar.com/Calendar.aspx">Agendas</a>'
                '<a href="/privacy-policy">Privacy</a>',
        "hosts": ["webchat-ui.citibot.net"],
    }]
    r = detect_site_metadata(pages, SCHEMA)
    assert r["agenda_platform"] == "legistar"
    assert r["agenda_client"] == "cityoflewisville"
    assert r["agenda_url"] == "https://cityoflewisville.legistar.com"
    assert r["cms"] == "WordPress"
    assert r["privacy_policy_url"] == "/privacy-policy"


def test_webapi_host_is_stoplisted():
    r = detect_site_metadata(
        [{"html": '<a href="https://webapi.legistar.com/v1/x/events">api</a>', "hosts": []}], SCHEMA)
    assert r["agenda_client"] == "" and r["agenda_platform"] == ""


def test_platform_detected_from_host_only():
    r = detect_site_metadata([{"html": "<html></html>", "hosts": ["frisco.civicclerk.com"]}], SCHEMA)
    assert r["agenda_platform"] == "civicclerk" and r["agenda_client"] == "frisco"


def test_empty_page_is_all_empty():
    r = detect_site_metadata([{"html": "<html>nothing</html>", "hosts": []}], SCHEMA)
    assert all(v == "" for v in r.values())


def test_mock_repo_roundtrips_metadata():
    repo = MockGovernanceRepository()
    t = repo.add_target("City of Lewisville", "TX", "cityoflewisville.com",
                        "https://cityoflewisville.com", [])
    repo.update_target(t["id"], {
        "agenda_platform": "legistar", "agenda_client": "cityoflewisville",
        "agenda_url": "https://cityoflewisville.legistar.com", "site_metadata_verified": True,
    })
    got = [x for x in repo.get_targets() if x["id"] == t["id"]][0]
    assert got["agenda_client"] == "cityoflewisville"
    assert got["agenda_platform"] == "legistar"
    assert got["site_metadata_verified"] is True
