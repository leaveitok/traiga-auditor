"""
test_chatbot_detection.py — Frase (branded) + unknown_chatbot (structural candidate).

Pinned to live evidence captured 2026-07-11:
  - odessa-tx.gov   → "Jett", Frase Answers iframe (answers-bot.frase.io)
  - midlandtexas.gov→ "Jacky", self-hosted bot on AWS Amplify (jacky-widget)

Guards the two false-clean fixes: a recognized vendor (Frase) fires as a normal
detection; an unrecognized self-hosted bot fires only as a CANDIDATE for review
and never as a branded/clean result. build_city_row must surface a candidate-only
city as review_needed — never no_ai_detected/compliant.
"""
from engine.crawler import PageCapture
from engine.fingerprint_engine import fingerprint
from engine.rule_loader import load_schema
from engine.scorecard import build_city_row

_S = load_schema()
_V = _S["AI_Vendor_Fingerprints"]["vendors"]
_T = _S["AI_Vendor_Fingerprints"]["match_threshold"]
_CFG = _S["scorecard_schema"]


def _cap(**k):
    d = dict(url="", html="", script_hosts=[], js_globals=[], iframe_origins=[],
             cookie_names=[], network_urls=[], text="", render_engine="playwright")
    d.update(k)
    return PageCapture(**d)


ODESSA = _cap(
    url="https://odessa-tx.gov/",
    html='<iframe id="frase-iframe" src="https://answers-bot.frase.io/924df58"></iframe>'
         '<script src="https://answers-script.frase.io/embed.js"></script>',
    script_hosts=["answers-script.frase.io", "www.googletagmanager.com"],
    iframe_origins=["https://answers-bot.frase.io"],
    network_urls=["https://answers-script.frase.io/embed.js"])

MIDLAND = _cap(
    url="https://www.midlandtexas.gov/",
    html='<iframe id="jacky-widget" src="https://main.dqy11vqq0k018.amplifyapp.com/widget"></iframe>',
    iframe_origins=["https://main.dqy11vqq0k018.amplifyapp.com"],
    network_urls=["https://main.dqy11vqq0k018.amplifyapp.com/widget"])

BENIGN = _cap(
    url="https://plaintown.gov/",
    html='<div class="news-widget">City News</div><iframe src="https://www.youtube.com/embed/x"></iframe>',
    iframe_origins=["https://www.youtube.com"], script_hosts=["www.youtube.com"])


def _ids(cap):
    return {d.vendor_id for d in fingerprint(cap, _V, _T)}


def test_frase_detected_on_odessa():
    assert "frase" in _ids(ODESSA)
    assert "unknown_chatbot" not in _ids(ODESSA)   # branded, not candidate


def test_unknown_chatbot_candidate_on_midland():
    ids = _ids(MIDLAND)
    assert "unknown_chatbot" in ids
    det = next(d for d in fingerprint(MIDLAND, _V, _T) if d.vendor_id == "unknown_chatbot")
    assert det.verification_status == "candidate_review"


def test_benign_page_stays_clean():
    assert _ids(BENIGN) == set()


def test_candidate_only_city_is_review_needed_not_clean():
    candidate_asset = [{"vendor_id": "unknown_chatbot", "display_name": "Unrecognized chatbot",
                        "verification_status": "candidate_review"}]
    row = build_city_row("Midland", "TX", "midlandtexas.gov",
                         candidate_asset, [], _CFG, crawl_ok=True)
    assert row["traiga_status"] == "review_needed"          # never no_ai_detected/compliant


def test_branded_asset_city_is_compliant_when_no_violations():
    branded = [{"vendor_id": "frase", "display_name": "Frase", "verification_status": "unverified_candidate"}]
    row = build_city_row("Odessa", "TX", "odessa-tx.gov", branded, [], _CFG, crawl_ok=True)
    assert row["traiga_status"] == "compliant"


def test_proxy_flag_recorded_on_row():
    row = build_city_row("X", "TX", "x.gov", [], [], _CFG, crawl_ok=True, used_proxy=True)
    assert row["last_scan_via_proxy"] is True
