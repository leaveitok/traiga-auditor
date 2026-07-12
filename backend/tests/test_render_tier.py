"""
test_render_tier.py — regression for the proxy render-tier escalation.

Austin (Imperva Incapsula) scan-failed: the static proxy tier can't solve a JS/
cookie WAF challenge. The fix is a render tier (ScraperAPI render=true) that the
pipeline auto-escalates to and then persists via a render_required target flag.
These tests pin the two pure/plumbing pieces: the proxy-URL transform and the
flag round-trip. (The pipeline wiring is covered by the live Austin re-scan.)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.crawler import _with_render


def test_with_render_injects_flag_into_username():
    out = _with_render("http://scraperapi:APIKEY@proxy-server.scraperapi.com:8001")
    assert out == "http://scraperapi.render=true:APIKEY@proxy-server.scraperapi.com:8001"


def test_with_render_is_idempotent():
    once = _with_render("http://scraperapi:APIKEY@proxy-server.scraperapi.com:8001")
    assert _with_render(once) == once  # already renders → unchanged


def test_with_render_preserves_existing_options():
    out = _with_render("http://scraperapi.country_code=us:APIKEY@proxy-server.scraperapi.com:8001")
    assert "render=true" in out and "country_code=us" in out


def test_with_render_noop_without_username():
    url = "http://proxy.example.com:8080"
    assert _with_render(url) == url


def test_render_required_flag_round_trips_via_update_target():
    from tests.mock_repository import MockGovernanceRepository
    repo = MockGovernanceRepository()
    t = repo.add_target("Austin", "TX", "austintexas.gov", "https://www.austintexas.gov", [])
    assert repo.update_target(t["id"], {"render_required": True}) is True
    saved = next(x for x in repo.get_targets() if x["id"] == t["id"])
    assert saved["render_required"] is True
