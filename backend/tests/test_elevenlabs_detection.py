"""
test_elevenlabs_detection.py — regression tests for the Grand Prairie false clean.

Fixtures replicate evidence captured from the LIVE www.gptx.org homepage on
2026-07-07 via real Chrome:
  - <script src="https://unpkg.com/@elevenlabs/convai-widget-embed"> loader
  - <elevenlabs-convai agent-id="agent_..."> custom element (shadow DOM, NO iframe)
  - runtime network calls to api.us.elevenlabs.io
  - script host is generic unpkg.com — must NOT be fingerprinted on its own
Deployed by integrator WhitegloveAI (city announcement 2026-05-04).
No network access required — pure unit tests (MockRepository principle).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.crawler import PageCapture
from engine.fingerprint_engine import fingerprint
from engine.rule_loader import load_schema

schema = load_schema()
VENDORS = schema["AI_Vendor_Fingerprints"]["vendors"]
THRESHOLD = schema["AI_Vendor_Fingerprints"]["match_threshold"]

# Rendered-DOM evidence as the Playwright crawler sees it (post-JS injection).
LIVE_HTML = """<html><head>
<script src="https://unpkg.com/@elevenlabs/convai-widget-embed" async type="text/javascript"></script>
</head><body>
<div id="monsido-pageassist" class="mon-logo-container mon-right"></div>
<elevenlabs-convai agent-id="agent_5901kvatk42kf93b8xbmep1ecq0k"></elevenlabs-convai>
</body></html>"""


def _detect(cap):
    return {d.vendor_id: d for d in fingerprint(cap, VENDORS, THRESHOLD)}


def test_elevenlabs_detected_from_rendered_html_only():
    # Worst case: crawler captured rendered HTML but no network URLs / globals.
    cap = PageCapture(url="https://www.gptx.org/Home", html=LIVE_HTML, text="Need help?")
    hits = _detect(cap)
    assert "elevenlabs_convai" in hits, "Grand Prairie regression: widget tag in HTML must fire"
    assert hits["elevenlabs_convai"].match_confidence >= THRESHOLD


def test_elevenlabs_detected_with_network_evidence():
    cap = PageCapture(
        url="https://www.gptx.org/Home",
        html=LIVE_HTML,
        text="Need help?",
        script_hosts=["heatmaps.monsido.com", "www.googletagmanager.com", "unpkg.com"],
        network_urls=["https://api.us.elevenlabs.io/v1/convai/agents"],
    )
    hits = _detect(cap)
    assert "elevenlabs_convai" in hits
    assert hits["elevenlabs_convai"].match_confidence >= 0.9


def test_unpkg_alone_does_not_fire():
    # unpkg.com serves half the internet; a random unpkg script is NOT ElevenLabs.
    cap = PageCapture(
        url="https://example.gov",
        html='<script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>',
        text="",
        script_hosts=["unpkg.com"],
    )
    assert "elevenlabs_convai" not in _detect(cap)


def test_clean_city_page_still_clean():
    cap = PageCapture(
        url="https://example.gov",
        html="<html><body><p>Agendas, minutes, and utility billing.</p></body></html>",
        text="Agendas, minutes, and utility billing.",
    )
    assert not _detect(cap)
