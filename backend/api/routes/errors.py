"""
errors.py — operational Error Log endpoints (platform-admin only).

Thin handler: reads the durable error log via the injected repository. The
audit log records governance actions (who did what); this log records
subsystem failures (what broke) for admin triage. Platform admins only —
fail-secure: anyone else gets 403.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/errors", tags=["errors"])


@router.get("")
def get_errors(
    limit: int = Query(default=100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Return operational error-log entries, most recent first (admin only)."""
    # TODO: attach verified user context for multi-tenant scoping (auth placeholder)
    principal = resolve_principal(user, repo)
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform administrator only.")

    rows = repo.get_error_log(limit=limit)
    for r in rows:
        # Mock returns a parsed `details`; Firestore/Sheets carry details_json.
        if "details" not in r:
            try:
                r["details"] = json.loads(r.get("details_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                r["details"] = {}
        r.pop("details_json", None)
    return rows
