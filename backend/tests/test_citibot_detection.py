"""
test_citibot_detection.py — regression tests for the Lewisville Citibot false negative.

Fixtures replicate evidence captured from the LIVE www.cityoflewisville.com
homepage on 2026-07-04 via real Chrome:
  - <script id="citibot-chatscript" src="https://webchat-ui.citibot.net/script.js?account_id=...">
  - <iframe id="citibot-chat-frame"> (no src — injected by the script)
  - "citibot" appears in HTML only; NEVER in visible page text
No network access required — pure unit tests (MockRepository principle).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.crawler import PageCapture, _hosts_from_html
from engine.fingerprint_engine import fingerprint
from engine.rule_loader import load_schema

schema = load_schema()
VENDORS = schema["AI_Vendor_Fingerprints"]["vendors"]
THRESHOLD = schema["AI_Vendor_Fingerprints"]["match_threshold"]

LIVE_HTML = """<html><head>
<style>@media (max-width: 767px) { iframe#citibot-chat-frame { bottom: 100px !important; } }</style>
<script async src="https://www.googletagmanager.com/gtm.js?id=GTM-T7JG59"></script>
<!--updated chatbot script--SF 07504421-->
<script id="citibot-chatscript" type="text/javascript" src="https://webchat-ui.citibot.net/script.js?account_id=68ac09329615b67e81037dc1"></script>
</head><body><h1>City of Lewisville, TX</h1><p>Adoptable Pets Building Permits Utility Bills</p>
<iframe id="citibot-chat-frame"></iframe></body></html>"""

VISIBLE_TEXT = "City of Lewisville, TX Adoptable Pets Building Permits Utility Bills"

# GTM container fragment with JSON-escaped script tag (how GTM encodes custom HTML tags)
GTM_FRAGMENT = '"vtp_html":"\\u003Cscript id=\\"citibot-chatscript\\" src=\\"https://webchat-ui.citibot.net/script.js?account_id=x\\"\\u003E"'


def _detected(cap):
    return {d.vendor_id: d for d in fingerprint(cap, VENDORS, THRESHOLD)}


def test_playwright_capture_detects_citibot():
    """Full Playwright-style capture: script host visible in DOM."""
    cap = PageCapture(
        url="https://www.cityoflewisville.com",
        html=LIVE_HTML,
        script_hosts=["www.googletagmanager.com", "webchat-ui.citibot.net",
                      "cdn.monsido.com", "govexperience.org"],
        network_urls=["https://webchat-ui.citibot.net/script.js?account_id=68ac09329615b67e81037dc1"],
        text=VISIBLE_TEXT,
        render_engine="playwright",
    )
    hits = _detected(cap)
    assert "citibot" in hits, f"Citibot not detected; got {list(hits)}"
    assert hits["citibot"].match_confidence >= THRESHOLD


def test_text_marker_fires_on_html_when_text_is_nonempty():
    """THE Lewisville false-negative bug: markers in HTML, page text non-empty."""
    cap = PageCapture(
        url="https://www.cityoflewisville.com",
        html=LIVE_HTML,
        script_hosts=[],          # DOM query missed it (async/late injection)
        text=VISIBLE_TEXT,        # non-empty → old engine never searched html
        render_engine="playwright",
    )
    hits = _detected(cap)
    assert "citibot" in hits, (
        "text_marker_regex must search HTML even when visible text is non-empty")


def test_static_tier_gtm_fragment_detection():
    """Datacenter-IP scenario: widget stripped from HTML, only GTM fragment present."""
    stripped_html = "<html><body><h1>City of Lewisville</h1></body></html>\n" + GTM_FRAGMENT
    cap = PageCapture(
        url="https://www.cityoflewisville.com",
        html=stripped_html,
        script_hosts=_hosts_from_html(stripped_html),
        text="City of Lewisville",
        render_engine="static",
    )
    hits = _detected(cap)
    assert "citibot" in hits, "GTM container fragment must be detectable"


def test_hosts_from_html_handles_escaped_quotes():
    hosts = _hosts_from_html(GTM_FRAGMENT)
    assert "webchat-ui.citibot.net" in hosts, f"got {hosts}"


def test_clean_city_no_false_positive():
    cap = PageCapture(
        url="https://www.example-city.gov",
        html="<html><body><h1>City Hall</h1><script src='https://cdn.civic-example.gov/site.js'></script></body></html>",
        script_hosts=["cdn.civic-example.gov"],
        text="City Hall — pay your water bill online",
        render_engine="playwright",
    )
    assert not _detected(cap), "clean city must not trigger detections"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
