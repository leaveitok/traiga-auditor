"""
bundle_spec.py — PURE evidence-bundle model builder (engine/, no I/O).

Turns a city's live governance data + an audience PRESET into a render-agnostic
`BundleModel` (nested dicts). The DOCX and PDF renderers walk that model; neither the
spec nor the renderers touch a repository, the network, or an LLM. This is what lets a
single engine serve every audience: the preset decides which section builders run and in
what order, and the same model renders to any format.

Two doctrines are enforced HERE, so no renderer or route can violate them:

1. PROVENANCE-FIRST. `provenance_summary` — what we DISCOVERED that was never declared —
   is emitted immediately after the cover. That is the page a self-attestation tool
   cannot produce, so it leads.

2. CANDIDATE, NOT VERDICT. Findings are candidate compliance signals requiring human and
   legal review, never enforcement determinations. Every section that states a finding
   carries that framing, and the full-depth presets end with a human ATTESTATION block.
   A renderer physically cannot print a "violation confirmed" verdict because the model
   never contains one.

Tamper-evidence: `content_hash()` is a SHA-256 over the canonical section content
(EXCLUDING the volatile generation timestamp), so identical findings always hash the
same. That hash identifies the findings — it is printed in the document and, in Phase 2,
stored on the snapshot for stale-detection and integrity.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PROVENANCE_LABELS = {
    "declared":                "Declared by city staff",
    "discovered_scan":         "Discovered — website scan",
    "discovered_oauth":        "Discovered — OAuth / shadow AI",
    "discovered_procurement":  "Discovered — procurement record",
    "discovered_agenda":       "Discovered — council agenda",
    "discovered_sentinel":     "Discovered — endpoint (Sentinel)",
    "discovered_budget":       "Discovered — budget document",
}

# The single sentence every finding-bearing bundle carries. Kept in one place so the
# candidate-not-verdict posture cannot drift between sections.
CANDIDATE_NOTICE = (
    "The findings in this document are candidate compliance signals produced by automated "
    "discovery. They require human and legal review and are not enforcement "
    "determinations. This tool is an out-of-line observer: it does not modify, submit to, "
    "or disrupt any target system."
)


def _is_discovered(provenance: str) -> bool:
    return bool(provenance) and provenance != "declared"


# ── Section builders — each PURE: (data) -> section dict, or None to omit ─────────────

def _sec_cover(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    sc = data.get("scorecard", {})
    return {
        "kind": "cover",
        "title": preset.get("title", "TRAIGA Compliance Report"),
        "city": sc.get("city", data.get("city", "")),
        "jurisdiction": sc.get("jurisdiction", "TX"),
        "audience": preset.get("audience", ""),
        "subtitle": "Texas HB 149 · Tex. Bus. & Com. Code Ch. 552 (TRAIGA)",
    }


def _sec_provenance_summary(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    assets = data.get("ai_assets", []) or []
    by_prov: Dict[str, int] = {}
    for a in assets:
        p = a.get("provenance") or ("declared" if a.get("declared") else "discovered_scan")
        by_prov[p] = by_prov.get(p, 0) + 1
    discovered = sum(n for p, n in by_prov.items() if _is_discovered(p))
    declared = by_prov.get("declared", 0)
    rows = [{"source": PROVENANCE_LABELS.get(p, p), "count": n,
             "discovered": _is_discovered(p)}
            for p, n in sorted(by_prov.items(), key=lambda kv: (-kv[1], kv[0]))]
    # The headline sentence — deliberately factual, never a verdict.
    def _n(n, sing="AI system", plur="AI systems"):
        return f"{n} {sing if n == 1 else plur}"
    _was = lambda n: "was" if n == 1 else "were"
    if discovered and declared:
        headline = (f"Of {_n(discovered + declared)} associated with this municipality, "
                    f"{discovered} {_was(discovered)} surfaced by automated discovery and "
                    f"{declared} {_was(declared)} declared by staff.")
    elif discovered:
        headline = (f"{_n(discovered)} {_was(discovered)} surfaced by automated discovery. "
                    f"None had been separately declared by staff.")
    elif declared:
        headline = (f"{_n(declared)} {'is' if declared == 1 else 'are'} on record, "
                    f"all declared by staff.")
    else:
        headline = ("No AI systems are currently on record for this municipality. Absence "
                    "of a finding is not proof of absence — see methodology.")
    return {
        "kind": "provenance_summary",
        "title": "What We Found — Discovered vs. Declared",
        "headline": headline,
        "discovered_count": discovered,
        "declared_count": declared,
        "rows": rows,
    }


def _sec_exec_status(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    sc = data.get("scorecard", {})
    violations = data.get("violations", []) or []
    open_v = [v for v in violations if v.get("status") in ("in_cure", "expired", "non_compliant")]
    urgent = sorted([v for v in open_v if isinstance(v.get("days_remaining"), int)],
                    key=lambda v: v.get("days_remaining"))
    facts = [
        {"label": "Municipality", "value": sc.get("city", data.get("city", ""))},
        {"label": "TRAIGA status", "value": str(sc.get("traiga_status", "not_assessed")).replace("_", " ").title()},
        {"label": "Open candidate findings", "value": str(len(open_v))},
        {"label": "Last assessed (UTC)", "value": str(sc.get("last_scanned_utc", "") or "").split("T")[0]},
    ]
    if urgent:
        d = urgent[0].get("days_remaining")
        facts.append({"label": "Nearest cure deadline", "value": f"{d} days remaining"})
    return {
        "kind": "exec_status",
        "title": "Executive Summary",
        "facts": facts,
        "notice": CANDIDATE_NOTICE,
        "background": (
            "Texas HB 149 (TRAIGA), Tex. Bus. & Com. Code Ch. 552, requires Texas "
            "governmental entities deploying public-facing AI to conspicuously disclose "
            "it. A 60-day cure period precedes any enforcement by the Texas Attorney "
            "General."),
    }


def _sec_asset_inventory(data: Dict[str, Any], preset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    assets = data.get("ai_assets", []) or []
    rows = []
    for a in assets:
        prov = a.get("provenance") or ("declared" if a.get("declared") else "discovered_scan")
        conf = a.get("match_confidence")
        rows.append({
            "vendor": a.get("display_name") or a.get("vendor_id") or "—",
            "type": (", ".join(a["asset_type"]) if isinstance(a.get("asset_type"), list)
                     else str(a.get("asset_type", "—"))),
            "source": PROVENANCE_LABELS.get(prov, prov),
            "confidence": (f"{float(conf) * 100:.0f}%" if isinstance(conf, (int, float)) else "—"),
            "status": a.get("verification_status", "candidate"),
            "location": a.get("page_url", ""),
        })
    return {
        "kind": "asset_inventory",
        "title": "AI Asset Inventory",
        "intro": ("Every AI system associated with the municipality, grouped by how it was "
                  "found. Discovered items are candidates for human confirmation."),
        "rows": rows,
        "empty": "No AI systems are currently on record.",
    }


def _sec_compliance_detail(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    sc = data.get("scorecard", {})
    return {
        "kind": "compliance_detail",
        "title": "Compliance Status Detail",
        "facts": [
            {"label": "TRAIGA status", "value": str(sc.get("traiga_status", "not_assessed")).replace("_", " ").title()},
            {"label": "Open candidate findings", "value": str(sc.get("open_violations_count", 0))},
            {"label": "Nearest cure deadline (days)", "value": str(sc.get("min_days_remaining", "—"))},
            {"label": "Last assessed (UTC)", "value": str(sc.get("last_scanned_utc", "—"))},
            {"label": "Domain assessed", "value": str(sc.get("domain", "—"))},
        ],
        "note": ("Status reflects automated assessment of public, observable signals only. "
                 "It is not a legal opinion."),
    }


def _sec_violations(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    violations = data.get("violations", []) or []
    open_v = [v for v in violations if v.get("status") in ("in_cure", "expired", "non_compliant")]
    items = []
    for v in open_v:
        ev = v.get("evidence", {}) if isinstance(v.get("evidence"), dict) else {}
        items.append({
            "rule_id": v.get("rule_id", "—"),
            "citation": v.get("citation", "—"),
            "severity": str(v.get("severity", "medium")).upper(),
            "status": str(v.get("status", "")).replace("_", " ").title(),
            "first_observed": str(v.get("first_observed_utc", "") or "").split("T")[0],
            "cure_deadline": str(v.get("cure_deadline_utc", "") or "").split("T")[0],
            "days_remaining": v.get("days_remaining"),
            "vendor": v.get("vendor_id", "—"),
            "page_url": ev.get("page_url", ""),
            "indicators": ev.get("matched_indicators", []) or [],
            "remediation": ev.get("remediation", ""),
        })
    return {
        "kind": "violations",
        "title": "Candidate Findings & Cure Period",
        "intro": (f"{len(open_v)} open candidate finding(s). Each carries a 60-day cure "
                  f"period from first observation per Tex. Bus. & Com. Code §552.053. "
                  f"These are candidates for review, not adjudicated violations."),
        "items": items,
        "empty": "No open candidate findings as of the last assessment.",
    }


def _sec_recommendations(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    violations = data.get("violations", []) or []
    recs, seen = [], set()
    for v in violations:
        ev = v.get("evidence", {}) if isinstance(v.get("evidence"), dict) else {}
        rem = (ev.get("remediation") or "").strip()
        if rem and rem not in seen:
            seen.add(rem)
            recs.append(rem)
    if not recs:
        recs = ["Confirm each discovered AI system, and where public-facing, add a "
                "conspicuous AI-use disclosure per TRAIGA."]
    return {"kind": "recommendations", "title": "Remediation Recommendations", "items": recs}


def _sec_statutory_reference(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "statutory_reference",
        "title": "Statutory Reference — TRAIGA Key Provisions",
        "items": [
            {"citation": "Tex. Bus. & Com. Code §552.051", "text": "Scope — governmental entities deploying AI that interacts with the public."},
            {"citation": "Tex. Bus. & Com. Code §552.052", "text": "Conspicuous disclosure of AI use to consumers."},
            {"citation": "Tex. Bus. & Com. Code §552.053", "text": "60-day cure period before Attorney General enforcement."},
        ],
    }


def _sec_methodology(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "methodology",
        "title": "Methodology & Limitations",
        "paragraphs": [
            "AI systems are identified through multiple independent discovery channels: "
            "public-website fingerprinting, identity-provider OAuth consent records, "
            "procurement and contract records, and published council agendas. Each finding "
            "records which channel produced it (its provenance).",
            "Findings are classified as candidates until a human confirms them. A candidate "
            "reflects an observed signal — for example a vendor script on a public page or "
            "a consented third-party application — not a legal conclusion. Confidence "
            "percentages reflect signal strength, not legal certainty.",
            "This tool is an out-of-line observer. It reads only public or "
            "customer-authorized data and never modifies, submits to, or disrupts a target "
            "system. Absence of a finding is not proof that no AI is in use.",
            CANDIDATE_NOTICE,
        ],
    }


def _sec_attestation(data: Dict[str, Any], preset: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "attestation",
        "title": "Reviewer Attestation",
        "statement": ("The findings above are automated candidate signals. By signing, the "
                      "reviewer attests that they have examined this report and applied "
                      "human judgement to its findings before any external use."),
        "fields": ["Reviewer name", "Title", "Signature", "Date"],
    }


_BUILDERS = {
    "cover": _sec_cover,
    "provenance_summary": _sec_provenance_summary,
    "exec_status": _sec_exec_status,
    "asset_inventory": _sec_asset_inventory,
    "compliance_detail": _sec_compliance_detail,
    "violations": _sec_violations,
    "recommendations": _sec_recommendations,
    "statutory_reference": _sec_statutory_reference,
    "methodology": _sec_methodology,
    "attestation": _sec_attestation,
}


def content_hash(sections: List[Dict[str, Any]]) -> str:
    """SHA-256 over canonical section content. Excludes volatile meta (timestamps), so
    identical findings hash identically — the property stale-detection relies on."""
    canonical = json.dumps(sections, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_fingerprint(data: Dict[str, Any]) -> str:
    """Hash of the SOURCE data (scorecard + assets + violations). Phase 2 compares this to
    the live value to flag a snapshot as stale."""
    payload = {
        "scorecard": data.get("scorecard", {}),
        "ai_assets": data.get("ai_assets", []),
        "violations": data.get("violations", []),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def build_bundle(data: Dict[str, Any], preset: Dict[str, Any], *,
                 tool_release: str = "dev",
                 generated_utc: Optional[str] = None) -> Dict[str, Any]:
    """PURE: (city data, preset def) -> BundleModel.

    Emits sections in the preset's declared order, enforcing provenance_summary directly
    after the cover regardless of preset ordering, so the doctrine cannot be mis-configured
    away. Unknown section keys are skipped rather than raising, so a new catalogue entry in
    SCHEMA_DEFINITION.json never crashes an old renderer.
    """
    ordered = list(preset.get("sections", []))
    # Enforce provenance-first: cover (if present) then provenance_summary lead.
    if "provenance_summary" in ordered:
        ordered.remove("provenance_summary")
        insert_at = 1 if (ordered and ordered[0] == "cover") else 0
        ordered.insert(insert_at, "provenance_summary")

    sections: List[Dict[str, Any]] = []
    for key in ordered:
        builder = _BUILDERS.get(key)
        if not builder:
            continue
        sec = builder(data, preset)
        if sec:
            sections.append(sec)

    chash = content_hash(sections)
    meta = {
        "doc_id": f"TRAIGA-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{chash[:6].upper()}",
        "preset_title": preset.get("title", "TRAIGA Compliance Report"),
        "audience": preset.get("audience", ""),
        "depth": preset.get("depth", "summary"),
        "is_package": bool(preset.get("package")),
        "city": data.get("scorecard", {}).get("city", data.get("city", "")),
        "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(),
        "tool_release": tool_release,
        "content_sha256": chash,
        "source_fingerprint": source_fingerprint(data),
        "attachments": list(preset.get("attachments", [])),
    }
    return {"meta": meta, "sections": sections}
