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


def _remember_agenda_source(repo, city: str, legistar_client: str) -> None:
    """Backstop: persist the Legistar slug the operator just used onto the city's
    target, so the agenda dialog pre-fills it next time and it is never re-typed.
    A slug the user actively ran with is authoritative → site_metadata_verified=True.
    Fully guarded — remembering the source must never fail the discovery response.

    # TODO: scope to the requesting user's jurisdiction (auth placeholder).
    """
    try:
        slug = (legistar_client or "").strip()
        if not slug:
            return
        want = str(city).strip().lower()
        for t in repo.get_targets():
            if str(t.get("city", "")).strip().lower() == want:
                repo.update_target(t.get("id"), {
                    "agenda_platform": "legistar",
                    "agenda_client": slug,
                    "agenda_url": f"https://{slug}.legistar.com",
                    "site_metadata_verified": True,
                })
                break
    except Exception as exc:
        print(f"[discovery] WARN: could not remember agenda source for {city}: "
              f"{type(exc).__name__}: {exc}")


class ProcurementRow(BaseModel):
    # Accept the common column names. The normalizer matches the PRODUCT/line-item
    # as well as the vendor, and runs an AI-keyword screen over both.
    vendor:      Optional[str] = None
    vendor_name: Optional[str] = None
    supplier:    Optional[str] = None
    company:     Optional[str] = None
    product:     Optional[str] = None
    description: Optional[str] = None
    line_item:   Optional[str] = None
    service:     Optional[str] = None
    item:        Optional[str] = None
    purpose:     Optional[str] = None
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
    written:    int
    matched:    int             # confident catalog matches
    candidates: int = 0         # AI-keyword hits flagged for human review
    skipped:    int
    rows:       int
    cities:     List[str]
    errors:     List[str]
    extractor:  Optional[str] = None   # which extractor actually ran (agenda only):
                                       # vertex | vertex_partial | keyword_fallback |
                                       # keyword | preextracted | none
    dry_run:    Optional[bool] = None  # oauth: true = reported only, NOTHING written


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
        candidates=result.get("candidates", 0),
        skipped=result["skipped"], rows=result["rows"],
        cities=result["cities"], errors=result["errors"],
    )


# ── Council-agenda discovery (separate engine; flag-gated) ────────────────────
# (extractor field on DiscoveryRunResponse is populated only by the agenda route)

class AgendaItem(BaseModel):
    # A council-agenda contract-award item (pre-extracted, or produced by the
    # server-side LLM extractor from raw agenda text).
    vendor:       Optional[str] = None
    product:      Optional[str] = None
    service:      Optional[str] = None
    action:       Optional[str] = None
    amount:       Optional[str] = None
    meeting_date: Optional[str] = None
    item_title:   Optional[str] = None
    source_url:   Optional[str] = None
    file_number:  Optional[str] = None
    contract_id:  Optional[str] = None


class AgendaRequest(BaseModel):
    city:            str
    legistar_client: Optional[str] = None   # e.g. "cityoflewisville" → Legistar Web API
    since:           Optional[str] = None    # YYYY-MM-DD (date window; default = lookback)
    until:           Optional[str] = None
    pdf_url:         Optional[str] = None    # agenda PDF (OnBase / CivicPlus etc.)
    agenda_url:      Optional[str] = None
    agenda_text:     Optional[str] = None
    items:           Optional[List[AgendaItem]] = None
    min_confidence:  float = 0.5


class OAuthGrant(BaseModel):
    # One consented application, provider-agnostic. Produced by the customer-run export
    # script (Door A) or a live read-only sync (Door B). NOTE: no user identities are
    # accepted here by default — `user_count` is the privacy-preserving answer to
    # "how many people consented"; `users` is opt-in and gated by include_users.
    app_id:     Optional[str] = None
    app_name:   Optional[str] = None
    publisher:  Optional[str] = None
    provider:   Optional[str] = None      # "microsoft" | "google"
    scopes:     List[str] = []
    user_count: Optional[int] = None
    users:      Optional[List[str]] = None
    first_seen: Optional[str] = None
    last_seen:  Optional[str] = None


class OAuthRequest(BaseModel):
    city:           str
    provider:       Optional[str] = None
    grants:         List[OAuthGrant]
    # Default DRY RUN: a pilot's first run must be able to show findings without
    # writing anything to the city's registry.
    dry_run:        bool = True
    include_users:  bool = False
    min_confidence: Optional[float] = None


@router.post("/oauth", response_model=DiscoveryRunResponse)
@limiter.limit("10/minute")
def run_oauth(
    request: Request,
    body: OAuthRequest,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Discover shadow AI from OAuth grants (an uploaded customer export, or a live sync)
    → registry as provenance=discovered_oauth. Flag-gated (OAUTH_DISCOVERY_ENABLED).
    RBAC: platform/agency admin, scoped to the city. DRY RUN by default — nothing is
    written unless the caller explicitly asks.
    """
    # TODO: attach verified user context for multi-tenant scoping (auth placeholder)
    principal = resolve_principal(user, repo)
    if not (principal.is_platform_admin or principal.is_agency_admin):
        raise HTTPException(
            status_code=403,
            detail="OAuth discovery requires platform_admin or agency_admin.")
    if not principal.all_cities and not principal.can_see_city(body.city):
        raise HTTPException(status_code=403, detail="City out of scope.")
    if len(body.grants) > 5000:
        raise HTTPException(status_code=400, detail="Too many grants (max 5000).")
    # Employee identities are a deliberate, platform-admin-only reveal.
    if body.include_users and not principal.is_platform_admin:
        raise HTTPException(
            status_code=403,
            detail="Including consenting-user identities requires platform_admin.")

    allowed_cities = None if principal.all_cities else principal.cities

    from core.discovery.oauth_source import run_oauth_discovery
    result = run_oauth_discovery(
        repo, body.city, [g.model_dump() for g in body.grants],
        provider=(body.provider or ""),
        dry_run=body.dry_run,
        include_users=body.include_users,
        min_confidence=body.min_confidence,
        allowed_cities=allowed_cities,
        actor=user.get("email", "unknown"),
    )
    if result.get("errors") == ["oauth_discovery_disabled"]:
        raise HTTPException(
            status_code=503,
            detail="OAuth discovery is disabled. Set OAUTH_DISCOVERY_ENABLED=true to enable.")

    return DiscoveryRunResponse(
        written=result["written"], matched=result["matched"],
        candidates=result.get("candidates", 0),
        skipped=result["skipped"], rows=result["rows"],
        cities=result["cities"], errors=result["errors"],
        dry_run=result.get("dry_run"),
    )


@router.post("/agenda", response_model=DiscoveryRunResponse)
@limiter.limit("10/minute")
def run_agenda(
    request: Request,
    body: AgendaRequest,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Discover AI from council-agenda contract-award items → registry as
    provenance=discovered_agenda. Separate engine, flag-gated
    (AGENDA_ENGINE_ENABLED). RBAC: platform/agency admin, scoped to the city.
    """
    # TODO: attach verified user context for multi-tenant scoping (auth placeholder)
    principal = resolve_principal(user, repo)
    if not (principal.is_platform_admin or principal.is_agency_admin):
        raise HTTPException(
            status_code=403,
            detail="Agenda discovery requires platform_admin or agency_admin.")
    if not principal.all_cities and not principal.can_see_city(body.city):
        raise HTTPException(status_code=403, detail="City out of scope.")

    allowed_cities = None if principal.all_cities else principal.cities

    from core.discovery.agenda_source import (
        run_agenda_discovery, run_legistar_discovery, run_pdf_discovery)
    if body.legistar_client:
        # End-to-end Legistar path: fetch the date window from the Web API.
        result = run_legistar_discovery(
            repo, body.city, body.legistar_client,
            since=body.since, until=body.until,
            min_confidence=body.min_confidence, allowed_cities=allowed_cities,
            actor=user.get("email", "unknown"),
        )
    elif body.pdf_url:
        # PDF agenda path (portals without an API).
        result = run_pdf_discovery(
            repo, body.city, body.pdf_url,
            min_confidence=body.min_confidence, allowed_cities=allowed_cities,
            actor=user.get("email", "unknown"),
        )
    else:
        items = [i.model_dump() for i in body.items] if body.items else None
        result = run_agenda_discovery(
            repo, body.city,
            items=items, agenda_text=body.agenda_text, agenda_url=body.agenda_url or "",
            min_confidence=body.min_confidence, allowed_cities=allowed_cities,
            actor=user.get("email", "unknown"),
        )
    if result.get("errors") == ["agenda_engine_disabled"]:
        raise HTTPException(
            status_code=503,
            detail="Agenda engine is disabled. Set AGENDA_ENGINE_ENABLED=true to enable.")

    # Backstop: remember the Legistar slug on the city so it is never re-typed.
    if body.legistar_client:
        _remember_agenda_source(repo, body.city, body.legistar_client)

    return DiscoveryRunResponse(
        written=result["written"], matched=result["matched"],
        candidates=result.get("candidates", 0),
        skipped=result["skipped"], rows=result["rows"],
        cities=result["cities"], errors=result["errors"],
        extractor=result.get("extractor"),
    )
