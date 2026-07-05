"""
auth_routes.py — Authentication and user-profile endpoints.

GET  /api/auth/me      — Verify token, return user role + city assignment.
POST /api/auth/users   — Admin: create or update a user's role/city assignment.
GET  /api/auth/users   — Admin: list all users.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_current_user, is_admin
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/auth", tags=["auth"])


class UserProfile(BaseModel):
    email: str
    role:  str           # "admin" | "city"
    city:  Optional[str] = None


class UserUpsertPayload(BaseModel):
    email: str
    role:  str
    city:  Optional[str] = None


@router.get("/me", response_model=UserProfile)
async def get_me(
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Return the authenticated user's role and city assignment.

    - If email is in ADMIN_EMAILS → role=admin.
    - Otherwise look up in the Users sheet.
    - If not found in Users sheet → auto-provision as city user and infer
      city from email domain matching a known target (best-effort).
    """
    email = user["email"]

    if is_admin(email):
        return UserProfile(email=email, role="admin", city=None)

    user_row = repo.get_user(email)

    if user_row:
        return UserProfile(
            email=email,
            role=user_row.get("role", "city"),
            city=user_row.get("city") or None,
        )

    # Auto-provision: try to match email domain to a target city
    domain = email.split("@")[-1].lower() if "@" in email else ""
    inferred_city: Optional[str] = None
    if domain:
        targets = repo.get_targets()
        for t in targets:
            target_domain = (t.get("domain") or t.get("url", "")).lower().replace("https://", "").replace("http://", "").rstrip("/")
            if domain in target_domain or target_domain in domain:
                inferred_city = t.get("city")
                break

    repo.upsert_user(email=email, role="city", city=inferred_city)
    return UserProfile(email=email, role="city", city=inferred_city)


@router.get("/users", response_model=List[UserProfile])
async def list_users(
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Admin only — list all provisioned users."""
    if not is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admin access required")
    # TODO: enforce admin-only read permission (auth placeholder)
    rows = repo.get_users()
    return [UserProfile(email=r["email"], role=r.get("role", "city"), city=r.get("city") or None) for r in rows]


@router.post("/users", response_model=UserProfile)
async def upsert_user(
    payload: UserUpsertPayload,
    user: Dict[str, Any] = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Admin only — create or update a user's role and city assignment."""
    if not is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admin access required")
    # TODO: enforce admin-only write permission (auth placeholder)
    repo.upsert_user(email=payload.email, role=payload.role, city=payload.city)
    try:
        repo.append_audit_log(
            event="user_role_changed", city_count=0, failures=0,
            details={"actor": user.get("email", "unknown"),
                     "summary": f"{payload.email} set to role={payload.role}"
                                + (f", city={payload.city}" if payload.city else ""),
                     "target_user": payload.email, "role": payload.role,
                     "city": payload.city})
    except Exception as exc:
        print(f"[activity] WARN: could not log user_role_changed: {exc}")
    return UserProfile(email=payload.email, role=payload.role, city=payload.city)
