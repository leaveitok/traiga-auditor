"""
cid.py — AG Civil Investigative Demand readiness + response derivation.

Legal basis (verified 2026-07-07 against enrolled HB 149):
  Tex. Bus. & Com. Code Sec. 552.103(b): pursuant to a CID the attorney general
  may request, per AI system — (1) purpose, intended use, deployment context,
  benefits; (2) type of data used to program/train; (3) categories of input
  data; (4) outputs produced; (5) performance evaluation metrics; (6) known
  limitations; (7) post-deployment monitoring and user safeguards; (8) other
  relevant documentation.
  Sec. 552.104(b)(2): cure statement — cured + supporting documentation of how
  + internal policy changes to prevent recurrence.

Design: per-asset, per-item tri-source answers — machine (derived from platform
data), attested (the cid_* / purpose / data-category human fields), or
vendor-referred (municipal reality: a city deploying a vendor chatbot cannot
know the vendor's training data; the honest answer is a referral, and that IS
an answer). Items left unanswerable are surfaced as gaps BEFORE any letter
arrives. Engineering artifact, not legal advice.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

CID_CITATION = "Tex. Bus. & Com. Code Sec. 552.103(b) (HB 149 enrolled; verified 2026-07-07)"
CURE_CITATION = "Tex. Bus. & Com. Code Sec. 552.104(b)(2) (HB 149 enrolled; verified 2026-07-07)"

CID_ITEMS = [
    {"item": "b1", "title": "Purpose, intended use, deployment context, and benefits"},
    {"item": "b2", "title": "Type of data used to program or train the system"},
    {"item": "b3", "title": "Categories of data processed as inputs"},
    {"item": "b4", "title": "Outputs produced by the system"},
    {"item": "b5", "title": "Metrics used to evaluate performance"},
    {"item": "b6", "title": "Known limitations of the system"},
    {"item": "b7", "title": "Post-deployment monitoring and user safeguards"},
    {"item": "b8", "title": "Other relevant documentation"},
]


def _parse_json_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        v = json.loads(raw or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _is_vendor_operated(asset: Dict[str, Any]) -> bool:
    """Discovered vendor systems: the city deploys but does not build/train."""
    provenance = str(asset.get("provenance", "")).lower()
    vendor = str(asset.get("vendor_id", "")).lower()
    return provenance in ("discovered", "discovered_scan", "") and bool(vendor) \
        and vendor not in ("generic_llm_chat",)


def _vendor_label(asset: Dict[str, Any]) -> str:
    return asset.get("display_name") or asset.get("vendor_id") or "the vendor"


def evaluate_asset(asset: Dict[str, Any], city_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Answer the eight 552.103(b) items for one asset.
    Each answer: {item, title, status: answered|gap, source: machine|attested|
    vendor_referred|composite, text}.
    """
    vendor_op = _is_vendor_operated(asset)
    types = _parse_json_list(asset.get("asset_types_json")) or ["ai_system"]
    cats = _parse_json_list(asset.get("data_categories_json"))
    answers: List[Dict[str, Any]] = []

    # b1 — purpose / intended use / context / benefits
    purpose = str(asset.get("purpose", "")).strip()
    context_bits = []
    if asset.get("page_url"):
        context_bits.append(f"deployed on {asset['page_url']}")
    if types:
        context_bits.append(f"system type: {', '.join(types)}")
    if purpose:
        answers.append({"status": "answered", "source": "attested",
                        "text": f"{purpose} ({'; '.join(context_bits)})" if context_bits else purpose})
    else:
        answers.append({"status": "gap", "source": None,
                        "text": "Purpose not yet documented — edit the asset and complete the Purpose field."})

    # b2 — training data
    td = str(asset.get("cid_training_data", "")).strip()
    if td:
        answers.append({"status": "answered", "source": "attested", "text": td})
    elif vendor_op:
        answers.append({"status": "answered", "source": "vendor_referred",
                        "text": f"Vendor-operated system supplied by {_vendor_label(asset)}. The city does not "
                                "program or train this system; training-data documentation is maintained by the "
                                "vendor, to whom this item is referred under the deployment agreement."})
    else:
        answers.append({"status": "gap", "source": None,
                        "text": "Training data not documented — complete the 'Training data' CID field."})

    # b3 — input data categories
    if cats:
        answers.append({"status": "answered", "source": "attested",
                        "text": f"Input data categories: {', '.join(cats)}."})
    elif "chatbot" in types or "virtual_assistant" in types:
        answers.append({"status": "answered", "source": "machine",
                        "text": "Free-text messages submitted by members of the public through the website chat "
                                "interface; no account or authentication data is required by the interface."})
    else:
        answers.append({"status": "gap", "source": None,
                        "text": "Input data categories not documented — set Data Categories on the asset."})

    # b4 — outputs
    out = str(asset.get("cid_outputs", "")).strip()
    if out:
        answers.append({"status": "answered", "source": "attested", "text": out})
    elif "chatbot" in types or "virtual_assistant" in types:
        answers.append({"status": "answered", "source": "machine",
                        "text": "Conversational text responses to resident inquiries (and voice output where the "
                                "widget supports it), generated in response to the input message."})
    else:
        answers.append({"status": "gap", "source": None,
                        "text": "Outputs not documented — complete the 'Outputs' CID field."})

    # b5 — performance metrics
    met = str(asset.get("cid_metrics", "")).strip()
    if met:
        answers.append({"status": "answered", "source": "attested", "text": met})
    else:
        answers.append({"status": "gap", "source": None,
                        "text": "Performance metrics not documented. If the city maintains none, state that and "
                                "note any vendor-managed metrics in the 'Metrics' CID field — an honest 'none' "
                                "is a complete answer; a blank is not."})

    # b6 — known limitations
    lim = str(asset.get("cid_limitations", "")).strip()
    if lim:
        answers.append({"status": "answered", "source": "attested", "text": lim})
    else:
        answers.append({"status": "gap", "source": None,
                        "text": "Known limitations not documented — complete the 'Known limitations' CID field."})

    # b7 — post-deployment monitoring (machine-composed; this is the platform's job)
    row = city_ctx.get("scorecard_row") or {}
    monitoring_bits = []
    if row.get("last_scanned_utc"):
        monitoring_bits.append(f"continuous automated external testing of public digital services "
                               f"(most recent assessment {str(row.get('last_scanned_utc'))[:10]})")
    monitoring_bits.append("statutory 60-day cure tracking for every finding")
    monitoring_bits.append("AI use-case inventory with owner attestation and annual review cadence")
    answers.append({"status": "answered", "source": "composite",
                    "text": "Post-deployment monitoring in effect: " + "; ".join(monitoring_bits) +
                            ". User safeguards: statutory AI-interaction disclosure verified by automated "
                            "disclosure testing (Sec. 552.051)."})

    # b8 — other documentation (always available: the platform's evidence trail)
    answers.append({"status": "answered", "source": "composite",
                    "text": "Scan evidence records, violation and remediation history, attestation records, and "
                            "the city's NIST AI RMF Alignment Statement are attached as appendices."})

    items_out = []
    for meta, ans in zip(CID_ITEMS, answers):
        items_out.append({**meta, **ans})
    gaps = [i for i in items_out if i["status"] == "gap"]
    return {
        "asset_key": asset.get("asset_key"),
        "display_name": asset.get("display_name") or asset.get("vendor_id") or asset.get("asset_key"),
        "vendor_operated": vendor_op,
        "items": items_out,
        "answered": len(items_out) - len(gaps),
        "total": len(items_out),
        "gaps": [g["item"] for g in gaps],
        "ready": not gaps,
    }


def evaluate_city(assets: List[Dict[str, Any]], city_ctx: Dict[str, Any]) -> Dict[str, Any]:
    active = [a for a in assets
              if str(a.get("lifecycle_status", "")).lower() != "retired"]
    per_asset = [evaluate_asset(a, city_ctx) for a in active]
    ready = [a for a in per_asset if a["ready"]]
    return {
        "citation": CID_CITATION,
        "assets": per_asset,
        "asset_count": len(per_asset),
        "ready_count": len(ready),
        "city_ready": len(ready) == len(per_asset) and len(per_asset) > 0,
    }
