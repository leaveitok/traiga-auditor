"""
logs.py — Audit Log endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("")
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    rows = repo.get_audit_log(limit=limit)
    scoped = []
    for r in rows:
        try:
            details = json.loads(r.get("details_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            details = {}
        # Scope: platform admins see everything; others see entries for their
        # cities plus their own actions. City-less system entries (e.g. user
        # role changes) are platform-admin only — fail-secure.
        if not principal.all_cities:
            entry_city = details.get("city")
            actor = details.get("actor")
            if entry_city is not None:
                if entry_city not in principal.cities:
                    continue
            elif actor != principal.email:
                continue
        r["details"] = details
        r.pop("details_json", None)
        scoped.append(r)
    return scoped
