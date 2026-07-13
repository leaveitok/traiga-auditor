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

from core import run_state as _rs


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
        agencies:   Optional[List[Dict[str, Any]]] = None,
        ai_assets:  Optional[List[Dict[str, Any]]] = None,
        error_log:  Optional[List[Dict[str, Any]]] = None,
    ):
        self._targets    = list(targets   or [])
        self._scorecard  = list(scorecard or [])
        self._violations = list(violations or [])
        self._audit_log  = list(audit_log  or [])
        self._error_log  = list(error_log  or [])
        self._users      = list(users      or [])
        self._agencies   = list(agencies   or [])
        self._ai_assets  = list(ai_assets  or [])
        self._run_state: Dict[str, Dict[str, Any]] = {}

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
        population: int = 0,
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
            "population":           int(population or 0),
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

    def update_target(self, target_id: str, fields: dict) -> bool:
        for t in self._targets:
            if t.get("id") == target_id:
                if "cloudflare_protected" in fields:
                    t["cloudflare_protected"] = bool(fields["cloudflare_protected"])
                if "tags" in fields:
                    t["tags"] = list(fields["tags"])
                if "population" in fields:
                    try:
                        t["population"] = int(float(fields["population"]))
                    except (TypeError, ValueError):
                        pass
                if "render_required" in fields:
                    t["render_required"] = bool(fields["render_required"])
                for _mk in ("agenda_platform", "agenda_client", "agenda_url", "cms", "privacy_policy_url"):
                    if _mk in fields:
                        t[_mk] = str(fields[_mk] or "").strip()
                if "site_metadata_verified" in fields:
                    t["site_metadata_verified"] = bool(fields["site_metadata_verified"])
                for _k in ("url", "city", "jurisdiction", "domain"):
                    if _k in fields and str(fields[_k]).strip():
                        t[_k] = str(fields[_k]).strip()
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

    # ── Error Log ─────────────────────────────────────────────────────────────

    def get_error_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        # Most recent first (mirrors Firestore/Sheets ordering).
        return list(reversed(self._error_log))[:limit]

    def append_error_log(self, source: str, message: str, level: str = "error",
                         city: Optional[str] = None,
                         details: Optional[Dict[str, Any]] = None) -> None:
        self._error_log.append({
            "level":        level,
            "source":       source,
            "message":      message,
            "city":         city or "",
            "details_json": "{}",
            "details":      details or {},
        })

    # ── User Management ───────────────────────────────────────────────────────

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        return next((u for u in self._users if u.get("email") == email), None)

    def upsert_user(self, email: str, role: str, city: Optional[str] = None,
                    agency_id: Optional[str] = None,
                    cities: Optional[List[str]] = None) -> None:
        # Signature mirrors the GovernanceRepository Protocol (multi-tenant:
        # cities list + agency_id; `city` retained as a legacy single-value
        # mirror = cities[0]). Prior drift here caused a TypeError on agency_id.
        city_list = list(cities) if cities is not None else ([city] if city else [])
        record = {
            "email":     email,
            "role":      role,
            "agency_id": agency_id or "",
            "cities":    city_list,
            "city":      (city_list[0] if city_list else None),  # legacy mirror
        }
        for u in self._users:
            if u.get("email") == email:
                u.update(record)
                return
        self._users.append(record)

    def get_users(self) -> List[Dict[str, Any]]:
        return list(self._users)

    def delete_user(self, email: str) -> bool:
        before = len(self._users)
        self._users = [u for u in self._users if u.get("email") != email]
        return len(self._users) < before

    # ── Agencies ──────────────────────────────────────────────────────────────

    def get_agencies(self) -> List[Dict[str, Any]]:
        return list(self._agencies)

    def get_agency(self, agency_id: str) -> Optional[Dict[str, Any]]:
        return next((a for a in self._agencies if a.get("id") == agency_id), None)

    def upsert_agency(self, agency_id: Optional[str], name: str,
                      granted_cities: List[str]) -> Dict[str, Any]:
        row = {"id": agency_id or str(len(self._agencies) + 1),
               "name": name, "granted_cities": list(granted_cities)}
        self._agencies = [a for a in self._agencies if a.get("id") != row["id"]]
        self._agencies.append(row)
        return row

    # ── Safe Harbor (Municipal AI Profile attestations) ───────────────────────

    def get_safe_harbor(self, city: str) -> List[Dict[str, Any]]:
        return [r for r in getattr(self, "_safe_harbor", [])
                if str(r.get("city", "")).lower() == city.lower()]

    def upsert_safe_harbor(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if not record.get("city") or not record.get("control_id"):
            raise ValueError("city and control_id are required")
        if not hasattr(self, "_safe_harbor"):
            self._safe_harbor = []
        key = (record["city"].lower(), record["control_id"])
        self._safe_harbor = [r for r in self._safe_harbor
                             if (r["city"].lower(), r["control_id"]) != key]
        self._safe_harbor.append(dict(record))
        return record

    # ── Durable run state (cross-instance in production; in-memory here) ──────

    def get_run_state(self, key: str) -> Dict[str, Any]:
        return dict(self._run_state.get(key, {}))

    def save_run_state(self, key: str, state: Dict[str, Any]) -> None:
        self._run_state[key] = dict(state)

    def claim_run_slot(self, key: str, now_utc: str, total: int,
                       stale_after_seconds: int) -> Optional[Dict[str, Any]]:
        existing = self._run_state.get(key, {})
        if not _rs.slot_available(existing, now_utc, stale_after_seconds):
            return None
        new_state = _rs.running_state(now_utc, total)
        self._run_state[key] = new_state
        return dict(new_state)

    # ── AI Use-Case Inventory ─────────────────────────────────────────────────

    def get_ai_assets(self, city: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = list(self._ai_assets)
        if city:
            rows = [r for r in rows if r.get("city") == city]
        return rows

    def upsert_ai_asset(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        key = asset.get("asset_key", "")
        if not key:
            raise ValueError("asset_key is required")
        existing = next((r for r in self._ai_assets
                         if r.get("asset_key") == key), {})
        merged = {**existing, **{k: v for k, v in asset.items() if v is not None}}
        self._ai_assets = [r for r in self._ai_assets if r.get("asset_key") != key]
        self._ai_assets.append(merged)
        return merged
