"""
violations.py — Violations & Cure Period endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from core.access import filter_rows, resolve_principal
from core.auth import get_current_user, is_admin
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/violations", tags=["violations"])


# ── Human-readable enrichment ────────────────────────────────────────────────
# Violations store vendor_id (a slug) and the raw indicators that fired. For the
# UI we resolve the vendor's friendly name + asset type from SCHEMA_DEFINITION.json
# (single source of truth) and translate indicator types into plain English, so a
# reviewer sees "This site uses Citibot (chatbot / virtual assistant)" rather than
# a slug. Resolved at read time so pre-existing violations benefit without a re-scan.
_VENDOR_MAP: Dict[str, Dict[str, Any]] | None = None

_INDICATOR_LABELS = {
    "script_host_regex":    "script host",
    "js_global_symbol":     "JavaScript global",
    "dom_selector":         "page element",
    "iframe_origin_regex":  "embedded iframe",
    "cookie_name_regex":    "cookie",
    "network_request_regex":"network request",
    "text_marker_regex":    "page-source marker",
}


def _vendor_map() -> Dict[str, Dict[str, Any]]:
    global _VENDOR_MAP
    if _VENDOR_MAP is None:
        try:
            from engine.rule_loader import load_schema
            vendors = load_schema()["AI_Vendor_Fingerprints"]["vendors"]
            _VENDOR_MAP = {v["vendor_id"]: v for v in vendors}
        except Exception:
            _VENDOR_MAP = {}
    return _VENDOR_MAP


def _enrich(v: Dict[str, Any]) -> Dict[str, Any]:
    try:
        v["evidence"] = json.loads(v.get("evidence_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        v["evidence"] = {}
    v.pop("evidence_json", None)

    # Friendly, reviewer-facing fields resolved from the governance schema.
    vendor_id = v.get("vendor_id", "") or ""
    vm = _vendor_map().get(vendor_id, {})
    display = vm.get("display_name") or (vendor_id.replace("_", " ").title() if vendor_id else "Unknown AI system")
    asset_types = vm.get("asset_types", []) or []
    asset_type = " / ".join(t.replace("_", " ") for t in asset_types) if asset_types else "AI system"
    v["vendor_display_name"] = display
    v["asset_type"] = asset_type
    v["finding_summary"] = f"This site uses {display} ({asset_type})."
    inds = (v.get("evidence") or {}).get("matched_indicators", []) or []
    signals: List[str] = []
    for ind in inds:
        itype = str(ind).split(":", 1)[0]
        label = _INDICATOR_LABELS.get(itype, itype)
        if label not in signals:
            signals.append(label)
    v["matched_signals"] = signals

    v["cure_period_status"] = v.get("cure_period_status", "True") == "True"
    v["needs_human_review"]  = v.get("needs_human_review", "True") == "True"
    try:
        v["days_remaining"] = int(v["days_remaining"]) if v.get("days_remaining") else None
    except (ValueError, TypeError):
        v["days_remaining"] = None
    return v


@router.get("")
def list_violations(
    status: Optional[str] = None,
    city: Optional[str] = None,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    rows = filter_rows(repo.get_violations(status=status, city=city), principal)
    enriched = [_enrich(r) for r in rows]
    enriched.sort(key=lambda r: (r["days_remaining"] is None, r["days_remaining"] or 9999))
    return enriched


@router.get("/{violation_id}")
def get_violation(
    violation_id: str,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    rows = repo.get_violations()
    for r in rows:
        if r.get("violation_id") == violation_id:
            if not principal.can_see_city(r.get("city")):
                raise HTTPException(status_code=404, detail="Violation not found")
            return _enrich(r)
    raise HTTPException(status_code=404, detail="Violation not found")


@router.delete("/admin/purge-dirty")
def purge_dirty_violations(
    pattern: str = "[BLOCKED",
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Admin-only: remove violation records whose domain field contains `pattern`.
    Used to clean up test artifacts (e.g. records where a JWT token was
    accidentally used as the domain value).
    """
    if not is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admin only")

    all_rows = repo.get_violations()
    clean = [r for r in all_rows if pattern not in str(r.get("domain", ""))]
    removed = len(all_rows) - len(clean)

    if removed:
        repo.write_violations(clean)

    return {"removed": removed, "remaining": len(clean)}
