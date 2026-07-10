"""
discovery.py — discovery-channel endpoints.

Thin handlers (project rule): enforce RBAC, resolve tenancy scope, call the
channel orchestrator via the injected repository. No business logic here — the
matching/merge logic lives in engine/collectors + core/discovery.

Channels ship incrementally; today: procurement. OAuth/network follow.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository, limiter
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/discovery", tags=["discovery"])


class ProcurementRow(BaseModel):
    # Accept the common column names; the normalizer reads vendor/vendor_name/supplier.
    vendor:      Optional[str] = None
    vendor_name: Optional[str] = None
    supplier:    Optional[str] = None
    city:        Optional[str] = None
    contract_id: Optional[str] = None
    amount:      Optional[str] = None
    term:        Optional[str] = None
    department:  Optional[str] = None


class ProcurementRequest(BaseModel):
    rows:           List[ProcurementRow]
    default_city:   Optional[str] = None
    min_confidence: float = 0.5


class DiscoveryRunResponse(BaseModel):
    written: int
    matched: int
    skipped: int
    rows:    int
    cities:  List[str]
    errors:  List[str]


@router.post("/procurement", response_model=DiscoveryRunResponse)
@limiter.limit("10/minute")
def run_procurement(
    request: Request,
    body: ProcurementRequest,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Discover procured AI from an uploaded vendor/spend/contract file (parsed to
    rows client-side, like Bulk Import). Merge matches into the AI inventory as
    provenance=discovered_procurement.

    RBAC: platform_admin or agency_admin only (write path). Matched cities are
    scoped to the principal's grant — fail-secure.
    """
    # TODO: attach verified user context for multi-tenant scoping (auth placeholder)
    principal = resolve_principal(user, repo)
    if not (principal.is_platform_admin or principal.is_agency_admin):
        raise HTTPException(
            status_code=403,
            detail="Procurement discovery requires platform_admin or agency_admin.")

    # Platform admin: all cities (None). Agency admin: only their granted cities.
    allowed_cities = None if principal.all_cities else principal.cities

    if not body.rows:
        raise HTTPException(status_code=400, detail="No rows supplied.")
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000).")

    # Lazy import via the single-swap registry keeps main.py wiring untouched.
    from core.discovery.procurement_source import run_procurement_discovery

    rows = [r.model_dump() for r in body.rows]
    result = run_procurement_discovery(
        repo, rows,
        default_city=(body.default_city or ""),
        min_confidence=body.min_confidence,
        allowed_cities=allowed_cities,
        actor=user.get("email", "unknown"),
    )
    return DiscoveryRunResponse(
        written=result["written"], matched=result["matched"],
        skipped=result["skipped"], rows=result["rows"],
        cities=result["cities"], errors=result["errors"],
    )
