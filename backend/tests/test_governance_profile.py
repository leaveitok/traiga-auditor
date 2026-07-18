"""
test_governance_profile.py — the vendor governance profile is SOURCED, not scored.

Guards the design decision that answers "how do we rate risk without knowing the
vendor's internals": (1) statutory_exposure only ever cites rule_ids that really exist
in the Compliance_Ruleset (a deterministic function->statute mapping, no vendor
internals); (2) the vocabulary keeps an explicit 'unknown'/'not_published' state so a
fact is never guessed; (3) NO composite numeric risk score is introduced.
"""
import json
import os

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "SCHEMA_DEFINITION.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    SCHEMA = json.load(_f)

GP = SCHEMA["Governance_Profile"]


def _all_rule_ids(obj, out):
    if isinstance(obj, dict):
        if isinstance(obj.get("rule_id"), str):
            out.add(obj["rule_id"])
        for v in obj.values():
            _all_rule_ids(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _all_rule_ids(x, out)


def test_exposure_cites_only_real_rules():
    ruleset_ids = set()
    _all_rule_ids(SCHEMA.get("Compliance_Ruleset"), ruleset_ids)
    referenced = set()
    for ids in GP["statutory_exposure"].values():
        referenced.update(ids)
    dangling = referenced - ruleset_ids
    assert not dangling, f"statutory_exposure cites non-existent rule_ids: {sorted(dangling)}"


def test_has_explicit_unknown_state():
    # A fact must be able to be 'unknown'/'not_published' — never forced to a guess.
    for s in ("documented", "not_published", "unknown"):
        assert s in GP["attribute_states"], f"missing honest state: {s}"


def _all_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k).lower())
            _all_keys(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _all_keys(x, out)


def test_no_fabricated_numeric_score():
    # Design guard: the profile must NOT introduce a computed risk number as a FIELD.
    # (The explanatory _comment may say the word "score"; we check keys, not prose.)
    keys = set()
    _all_keys(GP, keys)
    for banned in ("risk_score", "score", "rating", "risk_level", "risk_rating"):
        assert banned not in keys, f"governance profile must not define a '{banned}' field"


def test_core_functions_have_disclosure_exposure():
    # A conversational tool must map to the § 552.051 disclosure obligation.
    for fn in ("chatbot", "virtual_assistant", "conversational_ai"):
        ids = GP["statutory_exposure"][fn]
        assert any(i.startswith("EXT-DISCLOSURE") for i in ids), fn
    # A biometric/face tool must map to the biometric provision.
    for fn in ("biometric", "facial_recognition"):
        assert "EXT-BIOMETRIC-VISIBILITY-05" in GP["statutory_exposure"][fn], fn
