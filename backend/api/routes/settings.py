"""
settings.py — admin feature-flag / operational-settings endpoints.

Thin handlers: platform-admin only; read/write via core.settings (which stores
in the repository's key-value doc). Only allowlisted, NON-SENSITIVE toggles are
exposed — secrets never pass through here.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/admin/settings", tags=["settings"])


def _require_platform_admin(user: dict, repo: GovernanceRepository):
    # TODO: attach verified user context for multi-tenant scoping (auth placeholder)
    principal = resolve_principal(user, repo)
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform administrator only.")
    return principal


@router.get("")
def get_settings(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Return effective operational settings + the control schema for the UI."""
    _require_platform_admin(user, repo)
    from core import settings
    return {"settings": settings.get_all(repo), "schema": settings.public_schema()}


@router.put("")
def update_settings(
    body: Dict[str, Any],
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Persist allowlisted operational settings (platform admin only). Non-allowlisted
    keys are ignored; the change is written to the audit log.
    Accepts {"updates": {...}} or a flat {...} of key→value.
    """
    principal = _require_platform_admin(user, repo)
    from core import settings
    updates = body.get("updates") if isinstance(body.get("updates"), dict) else body
    effective = settings.save(repo, updates or {}, actor=principal.email)
    return {"settings": effective}
