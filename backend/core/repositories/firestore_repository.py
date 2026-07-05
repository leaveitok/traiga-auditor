"""
firestore_repository.py — Cloud Firestore implementation of GovernanceRepository.

Phase 2 storage backend (pre-planned in dependencies.py). Mirrors the semantics
of SheetsRepository exactly:

  * ALL field values are stored as strings. Sheets returns every cell as a
    string and downstream code (scorecard summary, active-flag checks, the
    frontend) was written against that contract. Preserving it means the
    storage swap is invisible above the repository layer.
  * Reads that Sheets served from full-tab scans are served here from
    collection streams; filtering stays in Python to match behavior 1:1
    (and to avoid composite-index management at MVP scale, ≤ ~1,200 cities).

Database: the named database config.FIRESTORE_GOVERNANCE_DB — "(default)" —
in the traiga-auditor project. Sentinel telemetry lives in a SEPARATE named
database (see firestore_sentinel_repository.py); the two datasets never share
a database, by design.

Document layout
───────────────
targets     doc id = target id (8-char uuid)
scorecard   doc id = city name ("/" replaced)
violations  doc id = violation_id
audit_log   auto id, ordered by timestamp_utc
users       doc id = lowercased email
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core import config

try:
    from google.cloud import firestore  # type: ignore
    from google.oauth2 import service_account  # type: ignore
    _FIRESTORE_AVAILABLE = True
except ImportError:
    _FIRESTORE_AVAILABLE = False

COLL_TARGETS    = "targets"
COLL_SCORECARD  = "scorecard"
COLL_VIOLATIONS = "violations"
COLL_AUDIT_LOG  = "audit_log"
COLL_USERS      = "users"

# google-cloud-firestore's Query.DESCENDING is literally this string; using the
# literal keeps every method testable against a fake client without the SDK.
_DESC = "DESCENDING"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_id(value: str) -> str:
    """Firestore doc IDs must not contain '/' and must not be '.' or '..'."""
    safe = str(value).replace("/", "_").strip()
    if safe in (".", "..", ""):
        safe = f"_{safe or 'blank'}_"
    return safe


class FirestoreRepository:
    """
    Cloud Firestore implementation of GovernanceRepository Protocol.
    Satisfies the Protocol via structural subtyping — no explicit inheritance.
    """

    def __init__(self) -> None:
        if not _FIRESTORE_AVAILABLE:
            raise RuntimeError(
                "google-cloud-firestore is not installed. "
                "Run: pip install google-cloud-firestore"
            )
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE
        )
        self._db = firestore.Client(
            project=config.FIRESTORE_PROJECT_ID or creds.project_id,
            credentials=creds,
            database=config.FIRESTORE_GOVERNANCE_DB,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _read_all(self, coll: str) -> List[Dict[str, Any]]:
        return [doc.to_dict() for doc in self._db.collection(coll).stream()]

    @staticmethod
    def _stringify(row: Dict[str, Any]) -> Dict[str, str]:
        """Store everything as strings — the SheetsRepository read contract."""
        return {k: str(v if v is not None else "") for k, v in row.items()}

    # ── GovernanceRepository Protocol implementation ──────────────────────────

    def ensure_schema(self) -> None:
        """Firestore collections are implicit — nothing to create."""
        return None

    def get_targets(self) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        rows = self._read_all(COLL_TARGETS)
        result = [r for r in rows if str(r.get("active", "true")).lower() != "false"]
        for r in result:
            raw = r.get("cloudflare_protected", "false")
            r["cloudflare_protected"] = str(raw).lower() in ("true", "1", "yes")
        return result

    def add_target(
        self,
        city: str,
        jurisdiction: str,
        domain: str,
        url: str,
        tags: List[str],
        cloudflare_protected: bool = False,
    ) -> Dict[str, Any]:
        # TODO: enforce admin-only write permission (auth placeholder)
        row = {
            "id":                   str(uuid.uuid4())[:8],
            "city":                 city,
            "jurisdiction":         jurisdiction,
            "domain":               domain,
            "url":                  url,
            "tags":                 json.dumps(tags),
            "added_utc":            _now_iso(),
            "active":               "true",
            "cloudflare_protected": str(cloudflare_protected).lower(),
        }
        self._db.collection(COLL_TARGETS).document(row["id"]).set(self._stringify(row))
        return {**row, "cloudflare_protected": cloudflare_protected, "active": True}  # type: ignore[dict-item]

    def deactivate_target(self, target_id: str) -> bool:
        # TODO: enforce admin-only write permission (auth placeholder)
        ref = self._db.collection(COLL_TARGETS).document(_doc_id(target_id))
        snap = ref.get()
        if not snap.exists:
            return False
        ref.update({"active": "false"})
        return True

    def get_scorecard(self) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        return self._read_all(COLL_SCORECARD)

    def get_scorecard_summary(self) -> Dict[str, Any]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        rows = self.get_scorecard()

        def _safe_score(v: Any) -> Optional[int]:
            try:
                return int(float(str(v))) if v not in (None, "", "None", "NaN") else None
            except (ValueError, TypeError):
                return None

        scores = [s for s in (_safe_score(r.get("compliance_score")) for r in rows)
                  if s is not None]
        return {
            "total_cities":             len(rows),
            "compliant":                sum(1 for r in rows if r.get("traiga_status") == "compliant"),
            "in_cure":                  sum(1 for r in rows if r.get("traiga_status") == "in_cure"),
            "non_compliant":            sum(1 for r in rows if r.get("traiga_status") == "non_compliant"),
            "expired":                  sum(1 for r in rows if r.get("traiga_status") == "expired"),
            "not_assessed":             sum(1 for r in rows if r.get("traiga_status") == "not_assessed"),
            "no_ai_detected":           sum(1 for r in rows if r.get("traiga_status") == "no_ai_detected"),
            "scan_failed":              sum(1 for r in rows if r.get("traiga_status") == "scan_failed"),
            "average_compliance_score": round(sum(scores) / len(scores), 1) if scores else None,
        }

    def delete_scorecard_row(self, city: str) -> bool:
        """Remove the scorecard doc for the given city. Returns True if deleted."""
        ref = self._db.collection(COLL_SCORECARD).document(_doc_id(city))
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def write_scorecard_rows(self, rows: List[Dict[str, Any]]) -> None:
        # TODO: enforce system-level write only (auth placeholder)
        for row in rows:
            doc = {
                "city":                  row["city"],
                "jurisdiction":          row.get("jurisdiction", ""),
                "domain":                row.get("domain", ""),
                "ai_assets_json":        json.dumps(row.get("ai_assets_detected", [])),
                "traiga_status":         row.get("traiga_status", "not_assessed"),
                "open_violations_count": len(row.get("open_violations", [])),
                "min_days_remaining":    row.get("min_days_remaining", ""),
                "compliance_score":      row.get("compliance_score", 100),
                "band":                  row.get("band", "green"),
                "last_scanned_utc":      row.get("last_scanned_utc", _now_iso()),
            }
            self._db.collection(COLL_SCORECARD).document(
                _doc_id(row["city"])
            ).set(self._stringify(doc))

    def get_violations(self, status: Optional[str] = None,
                       city: Optional[str] = None) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        rows = self._read_all(COLL_VIOLATIONS)
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if city:
            rows = [r for r in rows if str(r.get("city", "")).lower() == city.lower()]
        return rows

    def write_violations(self, violations: List[Dict[str, Any]]) -> None:
        # TODO: enforce system-level write only (auth placeholder)
        for v in violations:
            doc = {
                "violation_id":       v["violation_id"],
                "city":               v.get("city", ""),
                "domain":             v.get("domain", ""),
                "asset_id":           v.get("asset_id", ""),
                "vendor_id":          v.get("vendor_id", ""),
                "rule_id":            v.get("rule_id", ""),
                "citation":           v.get("citation", ""),
                "severity":           v.get("severity", "medium"),
                "first_observed_utc": v.get("first_observed_utc", ""),
                "cure_deadline_utc":  v.get("cure_deadline_utc", ""),
                "last_observed_utc":  v.get("last_observed_utc", ""),
                "days_remaining":     v.get("days_remaining", ""),
                "cure_period_status": str(v.get("cure_period_status", True)),
                "status":             v.get("status", "in_cure"),
                "evidence_json":      json.dumps(v.get("evidence", {})),
                "needs_human_review": str(v.get("needs_human_review", True)),
                "cured_utc":          v.get("cured_utc", ""),
            }
            self._db.collection(COLL_VIOLATIONS).document(
                _doc_id(v["violation_id"])
            ).set(self._stringify(doc))

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        docs = (self._db.collection(COLL_AUDIT_LOG)
                .order_by("timestamp_utc", direction=_DESC)
                .limit(limit).stream())
        return [d.to_dict() for d in docs]

    def append_audit_log(self, event: str, city_count: int,
                         failures: int, details: Dict[str, Any]) -> None:
        self._db.collection(COLL_AUDIT_LOG).add(self._stringify({
            "timestamp_utc": _now_iso(),
            "event":         event,
            "city_count":    city_count,
            "failures":      failures,
            "details_json":  json.dumps(details),
        }))

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        """Return the user doc for the given email, or None if not found."""
        snap = self._db.collection(COLL_USERS).document(_doc_id(email.lower())).get()
        return snap.to_dict() if snap.exists else None

    def upsert_user(self, email: str, role: str, city: Optional[str]) -> None:
        # TODO: enforce admin-only write permission (auth placeholder)
        ref = self._db.collection(COLL_USERS).document(_doc_id(email.lower()))
        snap = ref.get()
        created = (snap.to_dict() or {}).get("created_utc", "") if snap.exists else ""
        ref.set(self._stringify({
            "email":       email,
            "role":        role,
            "city":        city or "",
            "created_utc": created or _now_iso(),
        }))

    def get_users(self) -> List[Dict[str, Any]]:
        # TODO: enforce admin-only read permission (auth placeholder)
        return self._read_all(COLL_USERS)
