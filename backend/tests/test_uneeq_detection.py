"""
test_uneeq_detection.py — regression for the UneeQ digital-human signature.

Pinned to live evidence from www.amarillo.gov (2026-07-12): 'Emma' is a UneeQ
avatar loaded from cdn.uneeq.io with #uneeq-initial-container / #uneeqContainedLayout
containers. Before this signature the city scanned "No AI Detected" (false negative).
Runs against the REAL schema + fingerprint engine so the assertion is authoritative.
A benign control (YouTube embed) must stay clean so the signature can't false-positive.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.crawler import PageCapture
from engine.fingerprint_engine import fingerprint
from engine.rule_loader import load_schema

_S = load_schema()
_V = _S["AI_Vendor_Fingerprints"]["vendors"]
_T = _S["AI_Vendor_Fingerprints"]["match_threshold"]

_AMARILLO = PageCapture(
    url="https://www.amarillo.gov/",
    html='<script src="https://cdn.uneeq.io/hosted-experience/deploy/index.js"></script>'
         '<div id="uneeq-initial-container" class="MuiBox-root"><div id="uneeq-initial-content">'
         '<a>Learn more about Emma</a></div></div><div id="uneeqContainedLayout"></div>',
    script_hosts=["www.amarillo.gov", "cdn.uneeq.io", "docaccess.com"],
    text="Meet Emma Your Digital Assistant Chat with Emma Habla con Emma",
    render_engine="playwright",
)

_CONTROL = PageCapture(
    url="https://example-city.gov/",
    html='<iframe src="https://www.youtube.com/embed/abc123"></iframe><div class="hero">Welcome</div>',
    script_hosts=["www.youtube.com", "www.googletagmanager.com"],
    text="Welcome to our city",
    render_engine="playwright",
)


def test_uneeq_fires_on_amarillo():
    hits = {d.vendor_id: d for d in fingerprint(_AMARILLO, _V, _T)}
    assert "uneeq" in hits, f"UneeQ not detected; got {list(hits)}"
    assert hits["uneeq"].match_confidence >= _T


def test_uneeq_clean_on_benign_control():
    ids = {d.vendor_id for d in fingerprint(_CONTROL, _V, _T)}
    assert "uneeq" not in ids, f"UneeQ false-positive on control: {ids}"


def test_uneeq_script_host_fires_alone():
    """The cdn.uneeq.io loader alone must clear threshold (host-only capture)."""
    cap = PageCapture(url="https://x.gov/", script_hosts=["cdn.uneeq.io"], render_engine="playwright")
    ids = {d.vendor_id for d in fingerprint(cap, _V, _T)}
    assert "uneeq" in ids
