"""Regression: no_ai_detected vs scan_failed vs compliant (was all 'not_assessed')."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.scorecard import build_city_row
from engine.rule_loader import load_schema

CFG = load_schema()["scorecard_schema"]

def _row(assets, crawl_ok):
    return build_city_row("X", "TX", "x.gov", assets, [], CFG, crawl_ok=crawl_ok)["traiga_status"]

def test_crawl_ok_no_assets_is_no_ai_detected():
    assert _row([], crawl_ok=True) == "no_ai_detected"

def test_crawl_failed_no_assets_is_scan_failed():
    assert _row([], crawl_ok=False) == "scan_failed"

def test_assets_present_is_compliant_when_no_violations():
    assert _row([{"vendor_id": "citibot"}], crawl_ok=True) == "compliant"

def test_default_crawl_ok_true_backward_compatible():
    # Existing callers that omit crawl_ok must still behave as "assessed"
    assert build_city_row("X","TX","x.gov",[],[],CFG)["traiga_status"] == "no_ai_detected"

if __name__ == "__main__":
    fails=0
    for n,fn in sorted(globals().items()):
        if n.startswith("test_"):
            try: fn(); print("PASS", n)
            except AssertionError as e: fails+=1; print("FAIL", n, e)
    sys.exit(1 if fails else 0)
