"""
agencies.py — Agency (tenant organization) management. Platform-admin only.

An agency is granted a set of cities; its users can only ever be scoped to
cities within that grant (enforced in core.access).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.access import AccessDenied, assert_can_manage_agency, resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/agencies", tags=["agencies"])


class Agency(BaseModel):
    id:             Optional[str] = None
    name:           str
    granted_cities: List[str] = []


def _parse(a: Dict[str, Any]) -> Dict[str, Any]:
    raw = a.get("granted_cities")
    cities: List[str] = []
    if raw:
        try:
            v = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(v, list):
                cities = v
        except (json.JSONDecodeError, TypeError):
            cities = []
    return {"id": a.get("id"), "name": a.get("name", ""),
            "granted_cities": cities, "created_utc": a.get("created_utc", "")}


@router.get("")
def list_agencies(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Platform admin: all agencies. Agency admin: just their own (read)."""
    principal = resolve_principal(user, repo)
    agencies = [_parse(a) for a in repo.get_agencies() if a.get("id")]
    if principal.is_platform_admin:
        return agencies
    if principal.is_agency_admin:
        return [a for a in agencies if a["id"] == principal.agency_id]
    raise HTTPException(status_code=403, detail="Administrator access required")


@router.post("")
def upsert_agency(
    body: Agency,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    try:
        assert_can_manage_agency(principal)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    created = repo.upsert_agency(agency_id=body.id, name=body.name,
                                 granted_cities=body.granted_cities)
    try:
        repo.append_audit_log(
            event="agency_upserted", city_count=len(body.granted_cities), failures=0,
            details={"actor": principal.email,
                     "summary": f"Agency '{body.name}' granted {len(body.granted_cities)} cities",
                     "agency_id": created.get("id")})
    except Exception as exc:
        print(f"[activity] WARN: agency_upserted log failed: {exc}")
    return _parse({**created, "granted_cities": json.dumps(created.get("granted_cities", []))})
