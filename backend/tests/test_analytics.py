"""test_analytics.py — the pure analytics aggregator (vendor prevalence = the moat)."""
from core.analytics import build_analytics

SCORECARD = [
    {"city": "Lewisville", "traiga_status": "in_cure", "compliance_score": "80"},
    {"city": "Denton", "traiga_status": "compliant", "compliance_score": "100"},
    {"city": "Frisco", "traiga_status": "no_ai_detected", "compliance_score": ""},
]
VIOLATIONS = [
    {"city": "Lewisville", "status": "in_cure", "days_remaining": "12"},
    {"city": "Lewisville", "status": "in_cure", "days_remaining": "40"},
    {"city": "Denton", "status": "expired", "days_remaining": "-3"},
    {"city": "Denton", "status": "cured", "days_remaining": "5"},
]
ASSETS = [
    {"city": "Lewisville", "tool_id": "openai_chatgpt", "display_name": "ChatGPT", "provenance": "discovered_scan", "lifecycle_status": "attested"},
    {"city": "Denton", "tool_id": "openai_chatgpt", "display_name": "ChatGPT", "provenance": "discovered_sentinel", "lifecycle_status": "discovered"},
    {"city": "Frisco", "tool_id": "openai_chatgpt", "display_name": "ChatGPT", "provenance": "discovered_agenda", "lifecycle_status": "discovered"},
    {"city": "Lewisville", "tool_id": "citibot", "display_name": "Citibot", "provenance": "discovered_scan", "lifecycle_status": "attested"},
]


def test_totals_and_scores():
    r = build_analytics(SCORECARD, VIOLATIONS, ASSETS)
    assert r["totals"]["cities"] == 3
    assert r["totals"]["avg_score"] == 90.0
    assert r["totals"]["open_violations"] == 3     # 2 in_cure + 1 expired (cured excluded)
    assert r["totals"]["attested"] == 2 and r["totals"]["needs_attestation"] == 2


def test_vendor_prevalence_across_cities():
    r = build_analytics(SCORECARD, VIOLATIONS, ASSETS)
    top = r["vendor_prevalence"][0]
    assert top["tool_id"] == "openai_chatgpt" and top["city_count"] == 3   # the moat metric
    assert any(t["tool_id"] == "citibot" and t["city_count"] == 1 for t in r["vendor_prevalence"])


def test_provenance_and_cure_aging():
    r = build_analytics(SCORECARD, VIOLATIONS, ASSETS)
    assert {"discovered_scan", "discovered_sentinel", "discovered_agenda"} <= set(r["provenance_breakdown"])
    assert r["cure_aging"]["0-15 days"] == 1
    assert r["cure_aging"]["31-45 days"] == 1
    assert r["cure_aging"]["expired"] == 1
