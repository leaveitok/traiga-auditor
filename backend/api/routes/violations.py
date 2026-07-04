"""
violations.py — Violations & Cure Period endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from core.auth import get_current_user, is_admin
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/violations", tags=["violations"])


def _enrich(v: Dict[str, Any]) -> Dict[str, Any]:
    try:
        v["evidence"] = json.loads(v.get("evidence_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        v["evidence"] = {}
    v.pop("evidence_json", None)
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
    repo: GovernanceRepository = Depends(get_repository),
):
    # TODO: scope to requesting user's jurisdiction (auth placeholder)
    rows = repo.get_violations(status=status, city=city)
    enriched = [_enrich(r) for r in rows]
    enriched.sort(key=lambda r: (r["days_remaining"] is None, r["days_remaining"] or 9999))
    return enriched


@router.get("/{violation_id}")
def get_violation(
    violation_id: str,
    repo: GovernanceRepository = Depends(get_repository),
):
    # TODO: scope to requesting user's jurisdiction (auth placeholder)
    rows = repo.get_violations()
    for r in rows:
        if r.get("violation_id") == violation_id:
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
