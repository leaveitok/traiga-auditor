"""
test_incremental_pipeline.py — real-time per-city persistence + progress.

Product requirement (2026-07-05): dashboard must repaint during a scan
without manual refresh. The pipeline therefore persists each city's row and
violations as that city finishes, and reports per-city progress.
"""
from unittest.mock import patch

from engine.crawler import PageCapture
from engine.pipeline import run_full_audit

CITIBOT_HTML = ("<html><head>"
                "<script src='https://webchat-ui.citibot.net/script.js'></script>"
                "</head><body>" + ("<p>content</p>" * 120) +
                "<iframe id='citibot-chat-frame'></iframe></body></html>")


class RecordingRepo:
    """Records the ORDER of persistence calls to prove incrementality."""
    def __init__(self):
        self.calls = []            # ("scorecard", city) / ("violations", n) / ("audit_log",)
        self.scorecard_rows = []
    def get_violations(self, status=None, city=None): return []
    def write_scorecard_rows(self, rows):
        self.scorecard_rows.extend(rows)
        self.calls.extend(("scorecard", r["city"]) for r in rows)
    def write_violations(self, violations):
        self.calls.append(("violations", len(violations)))
    def append_audit_log(self, event, city_count, failures, details):
        self.calls.append(("audit_log",))


TARGETS = [
    {"city": "Alpha", "jurisdiction": "TX", "domain": "alpha.gov",
     "url": "https://alpha.gov", "cloudflare_protected": "false"},
    {"city": "Beta", "jurisdiction": "TX", "domain": "beta.gov",
     "url": "https://beta.gov", "cloudflare_protected": "false"},
]


def _fake_crawl(url, use_proxy=True, **kw):
    return [PageCapture(url=url, html=CITIBOT_HTML,
                        script_hosts=["webchat-ui.citibot.net"])]


def test_each_city_persisted_before_next_city_starts():
    repo = RecordingRepo()
    with patch("engine.crawler.crawl_site", side_effect=_fake_crawl), \
         patch("engine.config.SCAN_PROXY_URL", ""), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        run_full_audit(TARGETS, repo)
    sc_order = [c[1] for c in repo.calls if c[0] == "scorecard"]
    assert sc_order == ["Alpha", "Beta"], "rows must be written per city, in scan order"
    # Alpha's scorecard AND violations must land before Beta's scorecard
    beta_idx = repo.calls.index(("scorecard", "Beta"))
    assert ("scorecard", "Alpha") in repo.calls[:beta_idx]
    assert any(c[0] == "violations" for c in repo.calls[:beta_idx])
    assert repo.calls[-1] == ("audit_log",)


def test_progress_callback_reports_each_city_and_totals():
    repo = RecordingRepo()
    events = []
    with patch("engine.crawler.crawl_site", side_effect=_fake_crawl), \
         patch("engine.config.SCAN_PROXY_URL", ""), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        run_full_audit(TARGETS, repo, progress_cb=events.append)
    assert events[0] == {"current_city": "Alpha", "completed": 0, "total": 2, "proxy_active": False}
    assert events[-1] == {"current_city": "Beta", "completed": 2, "total": 2, "proxy_active": False}
    assert all(e["total"] == 2 for e in events)
    # No proxy is configured (SCAN_PROXY_URL patched empty) → never on the paid path.
    assert all(e["proxy_active"] is False for e in events)


def test_result_counts_unchanged_by_restructure():
    repo = RecordingRepo()
    with patch("engine.crawler.crawl_site", side_effect=_fake_crawl), \
         patch("engine.config.SCAN_PROXY_URL", ""), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        result = run_full_audit(TARGETS, repo)
    assert result["city_count"] == 2
    assert result["open_violations"] >= 2      # citibot disclosure violation per city
    assert len(repo.scorecard_rows) == 2


def test_broken_progress_callback_never_breaks_the_scan():
    repo = RecordingRepo()
    def bad_cb(_): raise RuntimeError("ui went away")
    with patch("engine.crawler.crawl_site", side_effect=_fake_crawl), \
         patch("engine.config.SCAN_PROXY_URL", ""), \
         patch("engine.config.SCAN_PROXY_ONLY_FLAGGED", True):
        result = run_full_audit(TARGETS, repo, progress_cb=bad_cb)
    assert result["city_count"] == 2
