"""
analytics.py — Analytics dashboard endpoint.

Thin handler: fetch repo reads, RBAC-scope to the principal's cities, and delegate
to the PURE core.analytics.build_analytics aggregator. No logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("")
def get_analytics(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Aggregate compliance + discovery analytics, scoped to visible cities."""
    # TODO: attach verified user context for multi-tenant scoping (auth placeholder)
    principal = resolve_principal(user, repo)
    scorecard = repo.get_scorecard()
    violations = repo.get_violations()
    assets = repo.get_ai_assets()

    if not principal.all_cities:
        cities = principal.cities
        scorecard = [r for r in scorecard if r.get("city") in cities]
        violations = [v for v in violations if v.get("city") in cities]
        assets = [a for a in assets if a.get("city") in cities]

    from core.analytics import build_analytics
    return build_analytics(scorecard, violations, assets)
