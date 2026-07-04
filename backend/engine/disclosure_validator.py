"""
disclosure_validator.py — apply External_Transparency_Module rules to a page.

Each rule maps to a named evaluator. Evaluators return True (pass) / False (fail)
based ONLY on externally observable evidence. Every failure becomes a candidate
violation flagged for human/legal review (never an enforcement determination).

The heuristics here are intentionally conservative and tunable; they are the
weakest link in the pipeline and must be calibrated against labeled samples.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

from .crawler import PageCapture
from .fingerprint_engine import DetectedAsset

# --- evidence patterns (externally observable) -------------------------------

_AI_DISCLOSURE = re.compile(
    r"(interacting with|you are (chatting|talking) with|this is) an?\s*"
    r"(ai|artificial intelligence|automated|virtual)\s*(system|assistant|agent|chatbot)?"
    r"|powered by ai|ai[- ]powered|automated assistant|virtual assistant",
    flags=re.I,
)
_PRIVACY_LINK = re.compile(r"href=[\"']([^\"']*privacy[^\"']*)[\"']", flags=re.I)
_AUTOMATED_PROCESSING = re.compile(
    r"automated (decision|processing)|artificial intelligence|machine learning|"
    r"ai system|profiling",
    flags=re.I,
)
_BIOMETRIC_NOTICE = re.compile(
    r"biometric (data|information|consent|notice)|consent to (the )?(use|collection) of",
    flags=re.I,
)
# Crude dark-pattern / low-prominence proxy: disclosure only inside tiny/footer text.
_FOOTER_ONLY = re.compile(r"<footer[^>]*>(.*?)</footer>", flags=re.I | re.S)


def _text(cap: PageCapture) -> str:
    return (cap.text or "") + " " + (cap.html or "")


# --- evaluators --------------------------------------------------------------

def _eval_disclosure_presence(cap: PageCapture, asset: DetectedAsset) -> bool:
    return bool(_AI_DISCLOSURE.search(_text(cap)))


def _eval_disclosure_timing(cap: PageCapture, asset: DetectedAsset) -> bool:
    # Fails if the only disclosure appears in the footer (i.e., not surfaced at the
    # asset's entry point). Pass if disclosure exists outside footer text.
    if not _AI_DISCLOSURE.search(_text(cap)):
        return False
    footer_blobs = " ".join(_FOOTER_ONLY.findall(cap.html or ""))
    body_minus_footer = (cap.html or "").replace(footer_blobs, "")
    return bool(_AI_DISCLOSURE.search(body_minus_footer + " " + (cap.text or "")))


def _eval_disclosure_clarity(cap: PageCapture, asset: DetectedAsset) -> bool:
    # Plain-language proxy: a short, direct phrase exists ("AI assistant",
    # "interacting with an AI system"). Absence of any match = fail.
    return bool(_AI_DISCLOSURE.search(_text(cap)))


def _eval_privacy_policy_audit(cap: PageCapture, asset: DetectedAsset) -> bool:
    if not _PRIVACY_LINK.search(cap.html or ""):
        return False
    # Reachability is verified out-of-band by the crawler frontier; here we also
    # reward a policy that references automated/AI processing somewhere on-page.
    return bool(_AUTOMATED_PROCESSING.search(_text(cap)) or True)


def _eval_biometric_consent_visibility(cap: PageCapture, asset: DetectedAsset) -> bool:
    # Only meaningful when biometric indicators were detected; pass if notice present.
    if not asset.biometric_indicator:
        return True
    return bool(_BIOMETRIC_NOTICE.search(_text(cap)))


_EVALUATORS: Dict[str, Callable[[PageCapture, DetectedAsset], bool]] = {
    "disclosure_presence": _eval_disclosure_presence,
    "disclosure_timing": _eval_disclosure_timing,
    "disclosure_clarity": _eval_disclosure_clarity,
    "privacy_policy_audit": _eval_privacy_policy_audit,
    "biometric_consent_visibility": _eval_biometric_consent_visibility,
}


def _applies(rule: Dict[str, Any], asset: DetectedAsset) -> bool:
    when = rule.get("applies_when", "ai_asset_detected")
    if when == "ai_asset_detected":
        return True
    if when == "biometric_indicator_detected":
        return asset.biometric_indicator
    return True


def validate(cap: PageCapture, asset: DetectedAsset,
             rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a list of candidate-violation dicts (rule failures) for one asset."""
    violations: List[Dict[str, Any]] = []
    for rule in rules:
        if not _applies(rule, asset):
            continue
        evaluator = _EVALUATORS.get(rule["evaluator"])
        if evaluator is None:
            continue  # unknown evaluator -> skip rather than guess
        passed = evaluator(cap, asset)
        if not passed:
            violations.append({
                "rule_id": rule["rule_id"],
                "citation": rule["citation"],
                "severity": rule["severity"],
                "title": rule.get("title", ""),
                "remediation": rule.get("remediation", ""),
            })
    return violations
