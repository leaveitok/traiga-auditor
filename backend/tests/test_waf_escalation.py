"""
test_waf_escalation.py — WAF auto-detection, proxy escalation, fail-secure status.

Product requirement (2026-07-05): an operator cannot know whether a city fronts
with Cloudflare. The scanner must detect the challenge itself, escalate to the
residential proxy automatically, and if it still cannot get real HTML report
scan_failed — NEVER no_ai_detected (silent false negative).
"""
import json
from unittest.mock import patch

from engine.crawler import PageCapture, is_waf_challenge
from engine.pipeline import run_full_audit

CHALLENGE_HTML = ("<html><head><title>Just a moment...</title>"
                  "<script src='/cdn-cgi/challenge-platform/h/b/orchestrate'></script>"
                  "</head><body>Checking your browser before accessing "
                  "cityoflewisville.com.</body></html>")

TINY_WAF_HTML = "<html><body>Access denied</body></html>"  # 302-byte-class page

REAL_CITIBOT_HTML = ("<html><head>"
                     "<script src='https://webchat-ui.citibot.net/script.js'></script>"
                     "</head><body>" + ("<p>City services content.</p>" * 100) +
                     "<iframe id='citibot-chat-frame'></iframe></body></html>")


def _cap(html, hosts=None, iframes=None):
    return PageCapture(url="https://www.cityoflewisville.com", html=html,
                       script_hosts=hosts or [], iframe_origins=iframes or [])


class FakeRepo:
    """Minimal GovernanceRepository double — records what the pipeline persists."""
    def __init__(self):
        self.scorecard_rows, self.violations, self.audit_events = [], [], []
    def get_violations(self, status=None, city=None): return []
    def write_scorecard_rows(self, rows): self.scorecard_rows.extend(rows)
    def write_violations(self, violations): self.violations.extend(violations)
    def append_audit_log(self, event, city_count, failures, details):
        self.audit_events.append(event)


TARGET = [{"city": "City of Lewisville", "jurisdiction": "TX",
           "domain": "cityoflewisville.com",
           "url": "https://www.cityoflewisville.com",
           "cloudflare_protected": "false"}]


# ── is_waf_challenge unit tests ───────────────────────────────────────────────

def test_detects_cloudflare_challenge_markers():
    assert is_waf_challenge(_cap(CHALLENGE_HTML)) is True


def test_detects_challenge_shape_tiny_page_no_surface():
    assert is_waf_challenge(_cap(TINY_WAF_HTML)) is True


def test_real_content_is_not_a_challenge():
    assert is_waf_challenge(_cap(REAL_CITIBOT_HTML,
                                 hosts=["webchat-ui.citibot.net"],
                                 iframes=["citibot-chat-frame"])) is False


def test_small_page_with_scripts_is_not_a_challenge():
    # Guard against over-triggering on legitimately small pages
    assert is_waf_challenge(_cap("<html><body>tiny</body></html>",
                                 hosts=["cdn.example.gov"])) is False


# ── pipeline escalation tests ────────────────────────────────────────────────

def test_waf_direct_then_proxy_escalation_finds_citibot():
    """Direct crawl hits WAF -> auto-escalate -> proxy sees real HTML -> violation."""
    calls = []
    def fake_crawl(url, use_proxy=True, **kw):
        calls.append(use_proxy)
        if not use_proxy:
            return [_cap(CHALLENGE_HTML)]
        return [_cap(REAL_CITIBOT_HTML, hosts=["webchat-ui.citibot.net"])]
    repo = FakeRepo()
    with patch("engine.crawler.crawl_site", side_effect=fake_crawl), \
         patch("engine.config.SCAN_PROXY_URL", "http://user:pw@proxy.example:8001"), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        run_full_audit(TARGET, repo)
    assert calls == [False, True], "expected direct attempt then proxy escalation"
    row = repo.scorecard_rows[0]
    assert row["traiga_status"] != "no_ai_detected"
    assets = json.loads(row["ai_assets_json"]) if isinstance(row.get("ai_assets_json"), str) \
             else row.get("ai_assets_detected", [])
    assert any(a.get("vendor_id") == "citibot" for a in assets)


def test_waf_with_no_proxy_scores_scan_failed_not_no_ai():
    """WAF challenge + no proxy configured -> scan_failed (fail-secure), never no_ai."""
    repo = FakeRepo()
    with patch("engine.crawler.crawl_site", return_value=[_cap(CHALLENGE_HTML)]), \
         patch("engine.config.SCAN_PROXY_URL", ""), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        run_full_audit(TARGET, repo)
    assert repo.scorecard_rows[0]["traiga_status"] == "scan_failed"


def test_waf_persisting_through_proxy_scores_scan_failed():
    """Even the proxy view is a challenge -> scan_failed, not no_ai_detected."""
    repo = FakeRepo()
    with patch("engine.crawler.crawl_site", return_value=[_cap(CHALLENGE_HTML)]), \
         patch("engine.config.SCAN_PROXY_URL", "http://proxy.example:8001"), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        run_full_audit(TARGET, repo)
    assert repo.scorecard_rows[0]["traiga_status"] == "scan_failed"


def test_clean_site_direct_no_escalation_single_call():
    """Real content on direct crawl -> exactly one crawl, no proxy spend."""
    calls = []
    def fake_crawl(url, use_proxy=True, **kw):
        calls.append(use_proxy)
        return [_cap(REAL_CITIBOT_HTML, hosts=["webchat-ui.citibot.net"])]
    repo = FakeRepo()
    with patch("engine.crawler.crawl_site", side_effect=fake_crawl), \
         patch("engine.config.SCAN_PROXY_URL", "http://proxy.example:8001"), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        run_full_audit(TARGET, repo)
    assert calls == [False], "clean direct crawl must not touch the paid proxy"
