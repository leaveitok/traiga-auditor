"""
scorecard.py — Compliance Scorecard endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

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
def get_scorecard(repo: GovernanceRepository = Depends(get_repository)):
    # TODO: scope to requesting user's jurisdiction (auth placeholder)
    return [_enrich(r) for r in repo.get_scorecard()]


@router.get("/summary")
def get_summary(repo: GovernanceRepository = Depends(get_repository)):
    # TODO: scope to requesting user's jurisdiction (auth placeholder)
    return repo.get_scorecard_summary()


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
    return {"deleted": city_name}
