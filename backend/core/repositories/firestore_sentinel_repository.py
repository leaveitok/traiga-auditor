"""
firestore_sentinel_repository.py — Cloud Firestore storage for AI-GRC Sentinel.

DATA SEPARATION IS THE POINT (same doctrine as sentinel_repository.py):
Sentinel packets are employee-level monitoring metadata — a different
sensitivity class from the external scanner's public findings. Therefore this
repository connects to a SEPARATE NAMED FIRESTORE DATABASE
(config.FIRESTORE_SENTINEL_DB, default "traiga-sentinel") in the same project.
Scanner data lives in "(default)". Distinct databases give physically separate
datasets, separate audit/quota boundaries, and a clean path to running
Sentinel under its own service account later.

Defense in depth is preserved: _assert_metadata_only() from
sentinel_repository.py runs on every write, and rows are projected onto the
fixed EVENT_HEADERS / HEARTBEAT_HEADERS field lists — unknown keys are
silently dropped, exactly as the Sheets implementation did.

Document IDs are the packet's event_id, which makes ingest IDEMPOTENT:
an extension retrying a queued packet overwrites the same doc instead of
duplicating the row (an improvement Sheets could not offer).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core import config
from core.repositories.sentinel_repository import (
    EVENT_HEADERS,
    HEARTBEAT_HEADERS,
    _assert_metadata_only,
    _now_iso,
)

try:
    from google.cloud import firestore  # type: ignore
    from google.oauth2 import service_account  # type: ignore
    _FIRESTORE_AVAILABLE = True
except ImportError:
    _FIRESTORE_AVAILABLE = False

COLL_EVENTS     = "events"
COLL_HEARTBEATS = "heartbeats"

# Query.DESCENDING is literally this string in google-cloud-firestore.
_DESC = "DESCENDING"

# When a Python-side filter (policy_id lives inside detections_json) must run
# before the limit, we fetch at most this many newest docs. At pilot scale this
# exceeds any realistic result set; revisit with composite indexes in Horizon 2.
_FETCH_CAP = 1000


class FirestoreSentinelRepository:
    """Cloud Firestore implementation of the SentinelRepository Protocol."""

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
            database=config.FIRESTORE_SENTINEL_DB,
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _project(row: Dict[str, Any], headers: List[str]) -> Dict[str, str]:
        """Keep only known fields, stringified — mirrors Sheets column projection."""
        return {h: str(row.get(h, "")) for h in headers}

    def _store(self, coll: str, headers: List[str], row: Dict[str, Any]) -> None:
        _assert_metadata_only(row)
        row.setdefault("received_utc", _now_iso())
        doc = self._project(row, headers)
        event_id = doc.get("event_id", "").replace("/", "_").strip()
        collection = self._db.collection(coll)
        if event_id and event_id not in (".", ".."):
            collection.document(event_id).set(doc)   # idempotent on retry
        else:
            collection.add(doc)

    # ── SentinelRepository Protocol implementation ───────────────────────────

    def ensure_schema(self) -> None:
        """Firestore collections are implicit — nothing to create."""
        return None

    def store_event(self, row: Dict[str, Any]) -> None:
        self._store(COLL_EVENTS, EVENT_HEADERS, row)

    def store_heartbeat(self, row: Dict[str, Any]) -> None:
        self._store(COLL_HEARTBEATS, HEARTBEAT_HEADERS, row)

    def get_events(self, policy_id: Optional[str] = None,
                   user_id: Optional[str] = None,
                   limit: int = 200) -> List[Dict[str, Any]]:
        import json as _json
        docs = (self._db.collection(COLL_EVENTS)
                .order_by("received_utc", direction=_DESC)
                .limit(_FETCH_CAP).stream())
        rows = [d.to_dict() for d in docs]
        if policy_id:
            def _has(r: Dict[str, Any]) -> bool:
                try:
                    return policy_id in {d.get("policy_id")
                                         for d in _json.loads(r.get("detections_json", "[]"))}
                except (_json.JSONDecodeError, TypeError):
                    return False
            rows = [r for r in rows if _has(r)]
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        return rows[:limit]

    def get_heartbeats(self, limit: int = 500) -> List[Dict[str, Any]]:
        docs = (self._db.collection(COLL_HEARTBEATS)
                .order_by("received_utc", direction=_DESC)
                .limit(limit).stream())
        return [d.to_dict() for d in docs]
