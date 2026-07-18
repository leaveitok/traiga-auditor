"""
test_ai_keywords_curated.py — curated high-precision AI keywords (governance-as-code).

Verifies the TRAIGA-relevant public-safety terms added to AI_Tool_Catalog.ai_keywords
fire on real procurement text, AND — the whole point of choosing them — that they do
NOT fire on generic "smart/intelligent" municipal buys that are not governance AI.
Uses the real schema + the real _keyword_hit screen (word-boundary match).
"""
import json
import os

from engine.collectors import identity
from engine.collectors.procurement import _keyword_hit

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "SCHEMA_DEFINITION.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    SCHEMA = json.load(_f)
KEYWORDS = identity.build_tool_index(SCHEMA).get("ai_keywords") or SCHEMA["AI_Tool_Catalog"]["ai_keywords"]

_CURATED = [
    "license plate recognition", "automated license plate", "alpr",
    "gunshot detection", "predictive policing", "speech recognition", "digital human",
]


def test_curated_terms_present():
    for kw in _CURATED:
        assert kw in KEYWORDS, f"missing curated keyword: {kw}"


def test_flags_real_public_safety_ai():
    hits = [
        "Award a Contract for an Automated License Plate Recognition (ALPR) System",
        "Resolution Approving Gunshot Detection Services with ShotSpotter",
        "Agreement for a Predictive Policing Analytics Platform",
        "Purchase of a Digital Human Virtual Assistant Kiosk",
    ]
    for text in hits:
        assert _keyword_hit(text, KEYWORDS) is not None, f"should flag: {text}"


def test_does_not_flag_generic_smart_buys():
    # Precision guard: the reason we did NOT add "smart"/"intelligent"/"camera".
    noise = [
        "Purchase of Smart Water Meters for the Utility District",
        "Intelligent Traffic Signal Timing Upgrade",
        "Smart Truck Camera Technology and Recycling Education",  # the McKinney item
        "Body-Worn Camera Replacement Program",
        "Automated External Defibrillator (AED) Purchase",
    ]
    for text in noise:
        assert _keyword_hit(text, KEYWORDS) is None, f"should NOT flag (noise): {text}"
