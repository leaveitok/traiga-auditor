"""
dependencies.py — FastAPI dependency providers.

TWO singletons live here:

  1. get_repository() — the single swap point for storage migration.
     Beta:     SheetsRepository  (Google Sheets + in-memory TTL cache)
     Phase 2:  FirestoreRepository  (Cloud Firestore, Python Admin SDK)

     Route modules declare:  repo: GovernanceRepository = Depends(get_repository)
     Tests override via:     app.dependency_overrides[get_repository] = lambda: MockRepository()

  2. limiter — the SlowAPI rate limiter singleton.
     Routes that need tighter-than-default limits import this and apply
     @limiter.limit("N/period") plus a Request parameter.

Nothing in this file may import from api/ or from concrete repository
implementations at module level (lazy import inside get_repository() only),
to prevent circular imports.
"""
from __future__ import annotations

from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address

from core.governance_service import GovernanceRepository

# ── Rate limiter ─────────────────────────────────────────────────────────────
# Default: 60 requests/minute per IP, applied via SlowAPIMiddleware in main.py.
# Phase 2: swap "memory://" for "redis://..." for multi-node deployments.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
)

# ── Storage singleton ─────────────────────────────────────────────────────────
_repo_instance: Optional[GovernanceRepository] = None


def get_repository() -> GovernanceRepository:
    """
    FastAPI dependency factory — returns a process-lifetime singleton.

    The singleton ensures the in-memory TTL cache in SheetsRepository
    survives across requests (cache is per-instance, not per-call).

    MIGRATION: Change the one line below to swap the entire platform backend:
        _repo_instance = FirestoreRepository()

    TESTING: Override per-test with:
        app.dependency_overrides[get_repository] = lambda: MockGovernanceRepository(...)

    TODO: inject verified user context for multi-tenant scoping (auth placeholder).
    """
    global _repo_instance
    if _repo_instance is None:
        # Lazy import — prevents circular imports since route modules import
        # this file, and SheetsRepository imports from core/ too.
        from core.repositories.sheets_repository import SheetsRepository
        _repo_instance = SheetsRepository()
    return _repo_instance
