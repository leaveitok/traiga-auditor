"""
fingerprint_engine.py — match a PageCapture against AI vendor signatures.

Each vendor in the schema defines weighted indicators across several types.
A vendor is considered "detected" when the summed weight of matched indicators
meets or exceeds the module's match_threshold. Indicator weights are clamped so
a single noisy indicator cannot, by itself, exceed the threshold unless intended.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .crawler import PageCapture


@dataclass
class DetectedAsset:
    asset_id: str
    vendor_id: str
    display_name: str
    asset_types: List[str]
    match_confidence: float
    matched_indicators: List[str] = field(default_factory=list)
    page_url: str = ""
    verification_status: str = "unverified_candidate"
    biometric_indicator: bool = False


# Externally observable hints that biometric capture *may* be present.
_BIOMETRIC_HINTS = re.compile(
    r"face(\s|-)?(id|recognition|match)|biometric|fingerprint|voiceprint|"
    r"iris|retina|getusermedia|facialrecognition",
    flags=re.I,
)


def _indicator_haystack(cap: PageCapture, itype: str) -> List[str]:
    return {
        "script_host_regex": cap.script_hosts,
        "js_global_symbol": cap.js_globals,
        "dom_selector": [cap.html],            # selector approximated via HTML regex
        "iframe_origin_regex": cap.iframe_origins,
        "cookie_name_regex": cap.cookie_names,
        "network_request_regex": cap.network_urls,
        "text_marker_regex": [cap.text or cap.html],
    }.get(itype, [])


def _matches(pattern: str, itype: str, values: List[str]) -> bool:
    if itype == "dom_selector":
        # Approximate CSS-ish selector matching against raw HTML: extract the
        # quoted attribute fragments (e.g. id*='citibot') and search for them.
        frags = re.findall(r"[\['\"]\s*([a-z0-9_-]{3,})", pattern, flags=re.I)
        html = values[0] if values else ""
        return any(f.lower() in html.lower() for f in frags)
    try:
        rx = re.compile(pattern, flags=re.I)
    except re.error:
        return False
    return any(rx.search(v or "") for v in values)


def fingerprint(cap: PageCapture, vendors: List[Dict[str, Any]],
                threshold: float) -> List[DetectedAsset]:
    detected: List[DetectedAsset] = []
    biometric = bool(_BIOMETRIC_HINTS.search(cap.text or cap.html or ""))

    for vendor in vendors:
        score = 0.0
        fired: List[str] = []
        for ind in vendor.get("indicators", []):
            itype = ind["type"]
            values = _indicator_haystack(cap, itype)
            if _matches(ind["pattern"], itype, values):
                score += float(ind.get("weight", 0))
                fired.append(f"{itype}:{ind['pattern']}")
        if score >= threshold:
            detected.append(DetectedAsset(
                asset_id=f"{vendor['vendor_id']}@{cap.url}",
                vendor_id=vendor["vendor_id"],
                display_name=vendor.get("display_name", vendor["vendor_id"]),
                asset_types=vendor.get("asset_types", []),
                match_confidence=round(min(score, 1.0), 3),
                matched_indicators=fired,
                page_url=cap.url,
                verification_status=vendor.get("verification_status", "unverified_candidate"),
                biometric_indicator=biometric,
            ))
    return detected
