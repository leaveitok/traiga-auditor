"""
scorecard.py — Compliance Scorecard endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from core.access import filter_rows, resolve_principal
from core.auth import get_current_user, is_admin
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/scorecard", tags=["scorecard"])


def _enrich(row: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON columns back into native types for the API response."""
    try:
        row["ai_assets"] = json.loads(row.get("ai_assets_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        row["ai_assets"] = []
    row.pop("ai_assets_json", None)
    return row


@router.get("")
def get_scorecard(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    rows = filter_rows(repo.get_scorecard(), principal)
    return [_enrich(r) for r in rows]


def _summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _score(v):
        try:
            return int(float(str(v))) if v not in (None, "", "None", "NaN") else None
        except (ValueError, TypeError):
            return None
    scores = [x for x in (_score(r.get("compliance_score")) for r in rows) if x is not None]
    def _n(st): return sum(1 for r in rows if r.get("traiga_status") == st)
    return {
        "total_cities": len(rows), "compliant": _n("compliant"),
        "in_cure": _n("in_cure"), "non_compliant": _n("non_compliant"),
        "expired": _n("expired"), "not_assessed": _n("not_assessed"),
        "no_ai_detected": _n("no_ai_detected"), "scan_failed": _n("scan_failed"),
        "average_compliance_score": round(sum(scores) / len(scores), 1) if scores else None,
    }


@router.get("/summary")
def get_summary(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    # Platform admin: use the repo's native (all-city) summary. Scoped users:
    # compute over only their visible rows so KPIs match what they can see.
    if principal.all_cities:
        return repo.get_scorecard_summary()
    return _summarize(filter_rows(repo.get_scorecard(), principal))


@router.delete("/{city_name}")
def delete_scorecard_row(
    city_name: str,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Admin-only: permanently remove a scorecard row by exact city name.
    Used to clean up orphan rows created by mismatched city name keys.
    """
    if not is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admin only")
    deleted = repo.delete_scorecard_row(city_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No scorecard row found for '{city_name}'")
    try:   # audit trail: a destructive admin delete must be recorded (logging never breaks the action)
        repo.append_audit_log(
            event="scorecard_row_deleted", city_count=1, failures=0,
            details={"actor": user.get("email", "unknown"),
                     "summary": f"Deleted scorecard row for {city_name}", "city": city_name})
    except Exception as exc:
        print(f"[scorecard] WARN: could not audit scorecard delete: {exc}")
    return {"deleted": city_name}
