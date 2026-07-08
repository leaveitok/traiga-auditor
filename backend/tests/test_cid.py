"""
test_cid.py — CID readiness derivation vs Tex. Bus. & Com. Code 552.103(b).

Contracts:
  - vendor-operated systems get an honest vendor-referral for (b2), which IS an
    answer (municipal reality: cities deploy, vendors train)
  - chatbots get machine answers for inputs (b3) and outputs (b4)
  - monitoring (b7) and documentation (b8) are always platform-composed
  - metrics (b5) and limitations (b6) require human fields; blanks are GAPS
  - readiness math and gap listing per asset and per city
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.cid import evaluate_asset, evaluate_city

CTX = {"scorecard_row": {"city": "Grand Prairie", "traiga_status": "in_cure",
                         "last_scanned_utc": "2026-07-07T12:00:00+00:00"}}

DISCOVERED_CHATBOT = {
    "asset_key": "elevenlabs_convai@https://www.gptx.org/Home",
    "display_name": "ElevenLabs Conversational AI",
    "vendor_id": "elevenlabs_convai",
    "provenance": "discovered",
    "asset_types_json": '["chatbot", "virtual_assistant"]',
    "page_url": "https://www.gptx.org/Home",
    "lifecycle_status": "attested",
    "purpose": "Resident self-service Q&A for city services",
    "data_categories_json": '["resident inquiries", "no PII solicited"]',
}


def test_vendor_chatbot_partial_readiness_and_gaps():
    r = evaluate_asset(DISCOVERED_CHATBOT, CTX)
    by = {i["item"]: i for i in r["items"]}
    assert by["b1"]["status"] == "answered" and by["b1"]["source"] == "attested"
    assert by["b2"]["status"] == "answered" and by["b2"]["source"] == "vendor_referred"
    assert "ElevenLabs" in by["b2"]["text"]
    assert by["b3"]["status"] == "answered"
    assert by["b4"]["status"] == "answered" and by["b4"]["source"] == "machine"
    assert by["b7"]["status"] == "answered" and "60-day cure" in by["b7"]["text"]
    assert by["b8"]["status"] == "answered"
    # metrics + limitations are human fields — blank means GAP
    assert by["b5"]["status"] == "gap" and by["b6"]["status"] == "gap"
    assert r["answered"] == 6 and r["gaps"] == ["b5", "b6"] and not r["ready"]


def test_completed_fields_reach_full_readiness():
    a = dict(DISCOVERED_CHATBOT)
    a["cid_metrics"] = "City maintains no independent metrics; vendor reports monthly deflection rate."
    a["cid_limitations"] = "English/Spanish/Vietnamese only; no case-specific legal or medical guidance."
    r = evaluate_asset(a, CTX)
    assert r["ready"] and r["answered"] == 8 and r["gaps"] == []


def test_missing_purpose_is_gap_b1():
    a = dict(DISCOVERED_CHATBOT); a["purpose"] = ""
    r = evaluate_asset(a, CTX)
    assert "b1" in r["gaps"]


def test_declared_internal_system_requires_training_data():
    a = {"asset_key": "d1", "display_name": "Internal doc summarizer",
         "vendor_id": "", "provenance": "declared",
         "asset_types_json": '["llm_interface"]',
         "purpose": "Staff document summarization",
         "data_categories_json": '["internal documents"]'}
    r = evaluate_asset(a, CTX)
    by = {i["item"]: i for i in r["items"]}
    assert by["b2"]["status"] == "gap"          # no vendor referral for city-run systems
    assert by["b4"]["status"] == "gap"          # non-chatbot outputs need documentation


def test_city_rollup_excludes_retired():
    retired = dict(DISCOVERED_CHATBOT, asset_key="old", lifecycle_status="retired")
    complete = dict(DISCOVERED_CHATBOT,
                    cid_metrics="none maintained", cid_limitations="languages limited")
    result = evaluate_city([retired, complete], CTX)
    assert result["asset_count"] == 1
    assert result["ready_count"] == 1
    assert result["city_ready"] is True
