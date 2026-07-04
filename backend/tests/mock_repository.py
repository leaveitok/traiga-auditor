"""
mock_repository.py — In-memory MockGovernanceRepository for unit tests.

Satisfies the GovernanceRepository Protocol via structural subtyping.
No Google Sheets, Firebase, or network connections required.

Usage in tests:
    from tests.mock_repository import MockGovernanceRepository

    mock = MockGovernanceRepository(
        targets=[{"id": "1", "city": "Test City", ...}],
        scorecard=[...],
        violations=[...],
    )
    app.dependency_overrides[get_repository] = lambda: mock
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class MockGovernanceRepository:
    """
    Pure in-memory implementation of GovernanceRepository Protocol.
    All state is mutable and inspectable — ideal for asserting side-effects.

    Inheriting from the Protocol is optional for structural subtyping,
    but explicit here to get the default get_scorecard_summary() implementation.
    """

    def __init__(
        self,
        targets:   Optional[List[Dict[str, Any]]] = None,
        scorecard: Optional[List[Dict[str, Any]]] = None,
        violations: Optional[List[Dict[str, Any]]] = None,
        audit_log:  Optional[List[Dict[str, Any]]] = None,
        users:      Optional[List[Dict[str, Any]]] = None,
    ):
        self._targets    = list(targets   or [])
        self._scorecard  = list(scorecard or [])
        self._violations = list(violations or [])
        self._audit_log  = list(audit_log  or [])
        self._users      = list(users      or [])

    # ── Schema ────────────────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        pass   # Nothing to initialise in memory

    # ── Target Registry ───────────────────────────────────────────────────────

    def get_targets(self) -> List[Dict[str, Any]]:
        return [t for t in self._targets if t.get("active", True)]

    def add_target(
        self,
        city: str,
        jurisdiction: str,
        domain: str,
        url: str,
        tags: List[str],
        cloudflare_protected: bool = False,
    ) -> Dict[str, Any]:
        row = {
            "id":                   str(len(self._targets) + 1),
            "city":                 city,
            "jurisdiction":         jurisdiction,
            "domain":               domain,
            "url":                  url,
            "tags":                 tags,
            "active":               True,
            "cloudflare_protected": cloudflare_protected,
            "added_utc":    "2026-01-01T00:00:00Z",
        }
        self._targets.append(row)
        return row

    def deactivate_target(self, target_id: str) -> bool:
        for t in self._targets:
            if t.get("id") == target_id:
                t["active"] = False
                return True
        return False

    # ── Scorecard ─────────────────────────────────────────────────────────────

    def get_scorecard(self) -> List[Dict[str, Any]]:
        return list(self._scorecard)

    def get_scorecard_summary(self) -> Dict[str, Any]:
        rows  = self.get_scorecard()
        total = len(rows)

        def _safe_score(v: Any) -> Optional[int]:
            try:
                return int(float(str(v))) if v not in (None, "", "None", "NaN") else None
            except (ValueError, TypeError):
                return None

        scores = [s for s in (_safe_score(r.get("compliance_score")) for r in rows) if s is not None]
        return {
            "total_cities":             total,
            "compliant":                sum(1 for r in rows if r.get("traiga_status") == "compliant"),
            "in_cure":                  sum(1 for r in rows if r.get("traiga_status") == "in_cure"),
            "non_compliant":            sum(1 for r in rows if r.get("traiga_status") == "non_compliant"),
            "expired":                  sum(1 for r in rows if r.get("traiga_status") == "expired"),
            "not_assessed":             sum(1 for r in rows if r.get("traiga_status") == "not_assessed"),
            "average_compliance_score": round(sum(scores) / len(scores), 1) if scores else None,
        }

    def write_scorecard_rows(self, rows: List[Dict[str, Any]]) -> None:
        existing = {r["city"]: r for r in self._scorecard}
        for row in rows:
            existing[row["city"]] = row
        self._scorecard = list(existing.values())

    def delete_scorecard_row(self, city: str) -> bool:
        before = len(self._scorecard)
        self._scorecard = [r for r in self._scorecard if r.get("city") != city]
        return len(self._scorecard) < before

    # ── Violations ────────────────────────────────────────────────────────────

    def get_violations(
        self,
        status: Optional[str] = None,
        city: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = list(self._violations)
        if status:
            result = [v for v in result if v.get("status") == status]
        if city:
            result = [v for v in result if v.get("city") == city]
        return result

    def write_violations(self, violations: List[Dict[str, Any]]) -> None:
        self._violations = list(violations)

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._audit_log[-limit:]

    def append_audit_log(
        self,
        event: str,
        city_count: int,
        failures: int,
        details: Dict[str, Any],
    ) -> None:
        self._audit_log.append({
            "event":       event,
            "city_count":  city_count,
            "failures":    failures,
            "details_json": "{}",
            "details":     details,
        })

    # ── User Management ───────────────────────────────────────────────────────

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._users if u.get("email") == email), None)

    def upsert_user(self, email: str, role: str, city: Optional[str]) -> None:
        for u in self._users:
            if u.get("email") == email:
                u["role"] = role
                u["city"] = city
                return
        self._users.append({"email": email, "role": role, "city": city})

    def get_users(self) -> List[Dict[str, Any]]:
        return list(self._users)
