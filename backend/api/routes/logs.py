"""
logs.py — Audit Log endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    repo: GovernanceRepository = Depends(get_repository),
):
    # TODO: scope to requesting user's jurisdiction (auth placeholder)
    rows = repo.get_audit_log(limit=limit)
    for r in rows:
        try:
            r["details"] = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            r["details"] = {}
        r.pop("details_json", None)
    return rows
