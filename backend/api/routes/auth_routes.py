"""
auth_routes.py — Authentication, user profile, and delegated user management.

  GET    /api/auth/me          — verify token, return caller's role + scope.
  GET    /api/auth/users       — list users the caller may administer.
  POST   /api/auth/users       — create/update a user (delegation-enforced).
  DELETE /api/auth/users/{email} — remove a user (delegation-enforced).

Authorization is centralized in core.access (resolve_principal / can_manage).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.access import (
    AccessDenied, ROLE_AGENCY_ADMIN, ROLE_PLATFORM_ADMIN, ROLE_VIEWER,
    assert_can_manage_user, resolve_principal,
)
from core.auth import get_current_user, is_admin
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/auth", tags=["auth"])


class UserProfile(BaseModel):
    email:     str
    role:      str
    agency_id: Optional[str] = None
    cities:    List[str] = []
    # legacy single-city field kept for older frontend builds
    city:      Optional[str] = None


class UserUpsertPayload(BaseModel):
    email:     str
    role:      str
    agency_id: Optional[str] = None
    cities:    List[str] = []


def _profile_from_principal(p) -> UserProfile:
    cities = sorted(p.cities) if not p.all_cities else []
    return UserProfile(email=p.email, role=p.role, agency_id=p.agency_id,
                       cities=cities, city=(cities[0] if cities else None))


@router.get("/me", response_model=UserProfile)
async def get_me(
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Return the authenticated caller's resolved role and city scope."""
    principal = resolve_principal(user, repo)
    # First-seen non-admin with no record → auto-provision as a viewer with no
    # cities (fail-secure: sees nothing until an admin grants access).
    if not principal.is_platform_admin:
        if repo.get_user(user["email"]) is None:
            try:
                repo.upsert_user(email=user["email"], role=ROLE_VIEWER,
                                 agency_id=None, cities=[])
            except Exception as exc:
                print(f"[auth] auto-provision failed for {user['email']}: {exc}")
    return _profile_from_principal(principal)


@router.get("/users", response_model=List[UserProfile])
async def list_users(
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """List users. Platform admin: all. Agency admin: their agency only."""
    principal = resolve_principal(user, repo)
    if principal.role not in (ROLE_PLATFORM_ADMIN, ROLE_AGENCY_ADMIN):
        raise HTTPException(status_code=403, detail="Administrator access required")

    import json
    def _cities(r):
        raw = r.get("cities")
        if raw:
            try:
                v = json.loads(raw)
                if isinstance(v, list):
                    return v
            except (json.JSONDecodeError, TypeError):
                pass
        return [r["city"]] if r.get("city") else []

    rows = repo.get_users()
    # De-dupe by email keeping the latest (Sheets append-wins); skip blanks.
    seen: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        em = (r.get("email") or "").strip()
        if em:
            seen[em.lower()] = r
    out = []
    for r in seen.values():
        if not principal.is_platform_admin and r.get("agency_id") != principal.agency_id:
            continue
        out.append(UserProfile(
            email=r["email"], role=r.get("role", ROLE_VIEWER),
            agency_id=r.get("agency_id") or None, cities=_cities(r),
            city=(r.get("city") or None)))
    return out


@router.post("/users", response_model=UserProfile)
async def upsert_user(
    payload: UserUpsertPayload,
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Create or update a user, bounded by the caller's delegation scope."""
    actor = resolve_principal(user, repo)
    # Agency admins implicitly assign users to their own agency.
    target_agency = payload.agency_id
    if actor.is_agency_admin and not target_agency:
        target_agency = actor.agency_id
    try:
        assert_can_manage_user(
            actor, target_email=payload.email, target_role=payload.role,
            target_agency_id=target_agency, target_cities=payload.cities, repo=repo)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    repo.upsert_user(email=payload.email, role=payload.role,
                     agency_id=target_agency, cities=payload.cities)
    try:
        repo.append_audit_log(
            event="user_upserted", city_count=0, failures=0,
            details={"actor": actor.email,
                     "summary": f"{payload.email} set to {payload.role}"
                                + (f" ({len(payload.cities)} cities)" if payload.cities else ""),
                     "target_user": payload.email, "role": payload.role,
                     "agency_id": target_agency})
    except Exception as exc:
        print(f"[activity] WARN: user_upserted log failed: {exc}")
    return UserProfile(email=payload.email, role=payload.role,
                       agency_id=target_agency, cities=payload.cities,
                       city=(payload.cities[0] if payload.cities else None))


@router.delete("/users/{email}", status_code=204)
async def delete_user(
    email: str,
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Remove a user, bounded by the caller's delegation scope."""
    actor = resolve_principal(user, repo)
    if is_admin(email):
        raise HTTPException(status_code=403, detail="Cannot remove a platform administrator.")
    target = repo.get_user(email) or {}
    try:
        assert_can_manage_user(
            actor, target_email=email, target_role=target.get("role", ROLE_VIEWER),
            target_agency_id=target.get("agency_id") or None,
            target_cities=[], repo=repo)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not repo.delete_user(email):
        raise HTTPException(status_code=404, detail="User not found")
    try:
        repo.append_audit_log(
            event="user_removed", city_count=0, failures=0,
            details={"actor": actor.email, "summary": f"Removed user {email}",
                     "target_user": email})
    except Exception as exc:
        print(f"[activity] WARN: user_removed log failed: {exc}")
