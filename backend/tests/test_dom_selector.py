"""Regression: dom_selector must match the vendor-specific token, not structural
markup ('class'/'id'/etc). Guards against CivicPlus (and any [class*=..] vendor)
false-firing on every page — the Frisco false-positive."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.crawler import PageCapture
from engine.fingerprint_engine import fingerprint, _matches
from engine.rule_loader import load_schema

S = load_schema(); V = S["AI_Vendor_Fingerprints"]["vendors"]; T = S["AI_Vendor_Fingerprints"]["match_threshold"]
_CP = [v for v in V if v["vendor_id"] == "civicplus"][0]
_CP_DOM = [i for i in _CP["indicators"] if i["type"] == "dom_selector"][0]["pattern"]

def test_dom_selector_does_not_fire_on_plain_class_attr():
    assert _matches(_CP_DOM, "dom_selector", ['<div class="anything">hi</div>']) is False

def test_civicplus_cms_attribution_is_not_a_violation():
    # Frisco: 'civicplus' present only as CMS platform credit + config, no widget
    html = ('<html><body class="cms">'
            '<input type="hidden" id="cpcDomain" value="https://x.civicplus.com">'
            '<span class="cpBylineTextTS">Government Websites by '
            '<a href="https://connect.civicplus.com/referral">CivicPlus</a></span></body></html>')
    cap = PageCapture(url="https://www.friscotexas.gov", html=html,
                      script_hosts=["docaccess.com"], text="Government Websites by CivicPlus")
    assert not [d for d in fingerprint(cap, V, T) if d.vendor_id == "civicplus"]

def test_real_civicplus_chatbot_still_detected():
    html = ('<html><body><div class="cp-chat-widget" data-civicplus="1"></div>'
            '<script src="https://widget.civicplus.com/chat.js"></script></body></html>')
    cap = PageCapture(url="https://city.gov", html=html,
                      script_hosts=["widget.civicplus.com"], text="chat")
    hits = {d.vendor_id: d for d in fingerprint(cap, V, T)}
    assert "civicplus" in hits and hits["civicplus"].match_confidence >= T

if __name__ == "__main__":
    fails = 0
    for n, fn in sorted(globals().items()):
        if n.startswith("test_"):
            try: fn(); print("PASS", n)
            except AssertionError as e: fails += 1; print("FAIL", n, e)
    sys.exit(1 if fails else 0)
