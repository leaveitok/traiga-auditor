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

    MIGRATION: backend selection is env-var driven (GOVERNANCE_STORE =
    "sheets" | "firestore") so rollback is a config change, not a revert.

    TESTING: Override per-test with:
        app.dependency_overrides[get_repository] = lambda: MockGovernanceRepository(...)

    TODO: inject verified user context for multi-tenant scoping (auth placeholder).
    """
    global _repo_instance
    if _repo_instance is None:
        # Lazy imports — prevent circular imports since route modules import
        # this file, and repository modules import from core/ too.
        from core import config
        if config.GOVERNANCE_STORE == "firestore":
            from core.repositories.firestore_repository import FirestoreRepository
            _repo_instance = FirestoreRepository()
        else:
            from core.repositories.sheets_repository import SheetsRepository
            _repo_instance = SheetsRepository()
    return _repo_instance


# ── Sentinel storage singleton (internal browser-DLP telemetry) ───────────────
# SEPARATE from get_repository() by design: Sentinel data is employee-level
# monitoring metadata and must never be reachable through the external-scan
# repository or its routes. Uses SENTINEL_SPREADSHEET_ID (own document).
_sentinel_repo_instance = None


def get_sentinel_repository():
    """
    FastAPI dependency factory for Sentinel telemetry storage.

    TESTING: override with
        app.dependency_overrides[get_sentinel_repository] = lambda: MemorySentinelRepository()
    """
    global _sentinel_repo_instance
    if _sentinel_repo_instance is None:
        from core import config
        if config.SENTINEL_STORE == "firestore":
            from core.repositories.firestore_sentinel_repository import (
                FirestoreSentinelRepository,
            )
            _sentinel_repo_instance = FirestoreSentinelRepository()
        else:
            from core.repositories.sentinel_repository import SheetsSentinelRepository
            _sentinel_repo_instance = SheetsSentinelRepository()
        try:
            _sentinel_repo_instance.ensure_schema()   # create tabs on first use (idempotent)
        except Exception as exc:
            print(f"[sentinel] ensure_schema failed (routes may 500 until fixed): {exc}")
    return _sentinel_repo_instance
