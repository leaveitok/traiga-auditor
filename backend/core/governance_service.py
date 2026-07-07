"""
governance_service.py — GovernanceRepository Protocol (interface definition).

This is the contract that ALL storage implementations must satisfy.
No route, engine, or utility module imports a concrete repository directly —
they depend only on this Protocol.

Swapping backends (Sheets → Firestore → Postgres) requires changing exactly
ONE line in main.py. This file never changes when storage changes.

Implementations:
    core/repositories/sheets_repository.py      ← Beta (Google Sheets)
    core/repositories/firestore_repository.py   ← Phase 2 (Cloud Firestore, Python Admin SDK)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class GovernanceRepository(Protocol):
    """
    Abstract interface for all governance data persistence operations.

    Every method signature here is stable across storage backends.
    Implementations must satisfy this Protocol — no inheritance required
    (structural subtyping via typing.Protocol).
    """

    # ── Schema / initialisation ───────────────────────────────────────────────

    def ensure_schema(self) -> None:
        """
        Initialise the storage backend on first run.
        - Sheets: create missing tabs, write header rows.
        - Firestore: create collections / indexes if absent.
        Must be idempotent — safe to call on every startup.
        """
        ...

    # ── Target Registry ───────────────────────────────────────────────────────

    def get_targets(self) -> List[Dict[str, Any]]:
        """Return all active audit targets.
        TODO: scope to requesting user's jurisdiction (auth placeholder).
        """
        ...

    def add_target(
        self,
        city: str,
        jurisdiction: str,
        domain: str,
        url: str,
        tags: List[str],
        cloudflare_protected: bool = False,
    ) -> Dict[str, Any]:
        """
        Add a new target to the registry.
        TODO: enforce admin-only write permission (auth placeholder).
        """
        ...

    def deactivate_target(self, target_id: str) -> bool:
        """
        Soft-delete a target (sets active=false).
        Returns True if found and deactivated, False if not found.
        TODO: enforce admin-only write permission (auth placeholder).
        """
        ...

    def update_target(self, target_id: str, fields: Dict[str, Any]) -> bool:
        """
        Update mutable scan settings on an existing target.
        Supported keys: cloudflare_protected (bool), tags (List[str]), url (str).
        Returns True if found and updated, False if not found.
        Route layer enforces platform_admin before calling.
        """
        ...

    # ── Compliance Scorecard ─────────────────────────────────────────────────

    def get_scorecard(self) -> List[Dict[str, Any]]:
        """
        Return all city scorecard rows (one per city, latest scan).
        TODO: scope to requesting user's jurisdiction (auth placeholder).
        """
        ...

    def get_scorecard_summary(self) -> Dict[str, Any]:
        """
        Return aggregate KPI counts: total, compliant, in_cure, expired, avg_score.
        Computed from get_scorecard() — implementations may override for efficiency.
        TODO: scope to requesting user's jurisdiction (auth placeholder).
        """
        rows = self.get_scorecard()
        total = len(rows)
        def _safe_score(v: Any) -> Optional[int]:
            try:
                return int(float(str(v))) if v not in (None, "", "None", "NaN") else None
            except (ValueError, TypeError):
                return None

        scores = [s for s in (_safe_score(r.get("compliance_score")) for r in rows)
                  if s is not None]
        return {
            "total_cities":               total,
            "compliant":                  sum(1 for r in rows if r.get("traiga_status") == "compliant"),
            "in_cure":                    sum(1 for r in rows if r.get("traiga_status") == "in_cure"),
            "non_compliant":              sum(1 for r in rows if r.get("traiga_status") == "non_compliant"),
            "expired":                    sum(1 for r in rows if r.get("traiga_status") == "expired"),
            "not_assessed":               sum(1 for r in rows if r.get("traiga_status") == "not_assessed"),
            "average_compliance_score":   round(sum(scores) / len(scores), 1) if scores else None,
        }

    def write_scorecard_rows(self, rows: List[Dict[str, Any]]) -> None:
        """
        Upsert scorecard rows after an audit run (keyed by city).
        TODO: enforce system-level write only — no user can call this directly (auth placeholder).
        """
        ...

    def delete_scorecard_row(self, city: str) -> bool:
        """
        Admin-only: permanently remove a scorecard row by city name.
        Used to clean up orphan rows created by mismatched city name keys.
        Returns True if a row was deleted, False if not found.
        """
        ...

    # ── Violations & Cure Period ─────────────────────────────────────────────

    def get_violations(
        self,
        status: Optional[str] = None,
        city: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return violation records, optionally filtered by status and/or city.
        Sorted by days_remaining ascending (most urgent first).
        TODO: scope to requesting user's jurisdiction (auth placeholder).
        """
        ...

    def write_violations(self, violations: List[Dict[str, Any]]) -> None:
        """
        Upsert violation records after an audit run (keyed by violation_id).
        TODO: enforce system-level write only (auth placeholder).
        """
        ...

    # ── Audit Log ────────────────────────────────────────────────────────────

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Return audit log entries, most recent first.
        TODO: scope to requesting user's jurisdiction (auth placeholder).
        """
        ...

    def append_audit_log(
        self,
        event: str,
        city_count: int,
        failures: int,
        details: Dict[str, Any],
    ) -> None:
        """
        Append one entry to the append-only audit log.
        TODO: enforce system-level write only (auth placeholder).
        """
        ...

    # ── User Management ───────────────────────────────────────────────────────

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Return a single user row by email, or None if not found.
        TODO: scope to admin-only or requesting user's own record (auth placeholder).
        """
        ...

    def upsert_user(self, email: str, role: str, city: Optional[str] = None,
                    agency_id: Optional[str] = None,
                    cities: Optional[List[str]] = None) -> None:
        """
        Create or update a user. role is platform_admin|agency_admin|viewer.
        `cities` is the viewer's granted city list (stored as JSON); `city`
        is retained for backward compatibility (mirrors cities[0]).
        Authorization is enforced by the route via core.access, not here.
        """
        ...

    def get_users(self) -> List[Dict[str, Any]]:
        """Return all provisioned users."""
        ...

    def delete_user(self, email: str) -> bool:
        """Remove a user. Returns True if a record was deleted."""
        ...

    # ── AI Use-Case Inventory ─────────────────────────────────────────────────

    def get_ai_assets(self, city: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return AI asset registry records, optionally filtered by city.
        Route-level RBAC scopes rows to the principal's visible cities.
        """
        ...

    def upsert_ai_asset(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update an asset record keyed by asset_key.

        MERGE CONTRACT: when the record exists, only the keys present in
        `asset` are written; absent keys are preserved. This is what lets a
        scan refresh machine fields (last_observed_utc, evidence, presence)
        without ever clobbering human fields (owner, attestation, purpose).
        Returns the merged record.
        """
        ...

    # ── Agencies (multi-tenant) ───────────────────────────────────────────────

    def get_agencies(self) -> List[Dict[str, Any]]:
        """Return all agencies (tenant orgs), each with granted_cities."""
        ...

    def get_agency(self, agency_id: str) -> Optional[Dict[str, Any]]:
        """Return a single agency by id, or None."""
        ...

    def upsert_agency(self, agency_id: Optional[str], name: str,
                      granted_cities: List[str]) -> Dict[str, Any]:
        """Create (agency_id None) or update an agency's name + city grant."""
        ...
