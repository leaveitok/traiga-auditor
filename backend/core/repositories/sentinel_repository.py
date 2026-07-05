"""
sentinel_repository.py — storage for AI-GRC Sentinel (internal browser-DLP) telemetry.

DATA SEPARATION IS THE POINT of this module. Sentinel packets are employee-level
monitoring metadata (user_id, device_id, policy tripped) — a different sensitivity
class from the external scanner's public findings. Therefore:

  * Separate spreadsheet: SENTINEL_SPREADSHEET_ID (falls back to SPREADSHEET_ID
    with a loud warning — acceptable for dev, not for production).
  * Separate repository/protocol: never mixed into GovernanceRepository, so no
    existing route can accidentally read Sentinel data.
  * Metadata only: the ingest route's Pydantic model (extra='forbid') rejects any
    packet carrying raw text, filenames, hashes, or URL paths. Enforced again here
    via _FORBIDDEN_FRAGMENTS as defense in depth.

Implementations:
  SheetsSentinelRepository — Google Sheets tabs SentinelEvents / SentinelHeartbeats
  MemorySentinelRepository — tests / local dev without Google credentials
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

SHEET_EVENTS = "SentinelEvents"
SHEET_HEARTBEATS = "SentinelHeartbeats"

EVENT_HEADERS = [
    "event_id", "timestamp_utc", "received_utc", "device_id", "user_id",
    "browser_name", "browser_version", "extension_version", "ruleset_version",
    "site_id", "origin", "trigger", "payload_class",
    "file_ext", "file_size_bytes", "file_scannable",
    "detections_json", "action_taken",
]
HEARTBEAT_HEADERS = [
    "event_id", "timestamp_utc", "received_utc", "device_id", "user_id",
    "extension_version", "ruleset_version", "policies_loaded",
    "last_scan_utc", "status",
]

# Belt-and-suspenders: no stored field may carry these key fragments.
_FORBIDDEN_FRAGMENTS = ("prompt", "matched_text", "file_name", "filename", "sha256", "content")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_metadata_only(row: Dict[str, Any]) -> None:
    for k in row:
        lk = k.lower()
        if any(f in lk for f in _FORBIDDEN_FRAGMENTS):
            raise ValueError(f"Sentinel storage rejects prohibited field: {k}")


@runtime_checkable
class SentinelRepository(Protocol):
    """Contract for Sentinel telemetry persistence. Mirrors GovernanceRepository style."""

    def ensure_schema(self) -> None: ...
    def store_event(self, row: Dict[str, Any]) -> None: ...
    def store_heartbeat(self, row: Dict[str, Any]) -> None: ...
    def get_events(self, policy_id: Optional[str] = None,
                   user_id: Optional[str] = None,
                   limit: int = 200) -> List[Dict[str, Any]]: ...
    def get_heartbeats(self, limit: int = 500) -> List[Dict[str, Any]]: ...


class MemorySentinelRepository:
    """In-memory implementation for tests and credential-less local dev."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.heartbeats: List[Dict[str, Any]] = []

    def ensure_schema(self) -> None:
        return None

    def store_event(self, row: Dict[str, Any]) -> None:
        _assert_metadata_only(row)
        self.events.append(dict(row))

    def store_heartbeat(self, row: Dict[str, Any]) -> None:
        _assert_metadata_only(row)
        self.heartbeats.append(dict(row))

    def get_events(self, policy_id=None, user_id=None, limit=200):
        rows = self.events
        if policy_id:
            rows = [r for r in rows
                    if policy_id in {d.get("policy_id") for d in json.loads(r.get("detections_json", "[]"))}]
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        return list(reversed(rows))[:limit]

    def get_heartbeats(self, limit=500):
        return list(reversed(self.heartbeats))[:limit]


class SheetsSentinelRepository:
    """
    Google Sheets implementation. Tabs live in the Sentinel spreadsheet
    (SENTINEL_SPREADSHEET_ID) so internal DLP data never shares a document
    with the external transparency scorecard.
    """

    def __init__(self) -> None:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        from core import config

        self._spreadsheet_id = os.environ.get("SENTINEL_SPREADSHEET_ID", "").strip()
        if not self._spreadsheet_id:
            print("[sentinel] WARNING: SENTINEL_SPREADSHEET_ID not set — falling back to "
                  "SPREADSHEET_ID. Use a dedicated spreadsheet in production (data separation).")
            self._spreadsheet_id = config.SPREADSHEET_ID
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self._svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._sheet = self._svc.spreadsheets()
        # httplib2 (under googleapiclient) is NOT thread-safe. Cloud Run serves
        # requests concurrently and the frontend fires events+summary+devices in
        # parallel; without this lock the shared connection deadlocks. Mirrors the
        # serialization used by the main SheetsRepository.
        self._lock = threading.RLock()

    # ── generic helpers (same shape as core/sheets.py) ────────────────────────
    def _read_all(self, tab: str) -> List[Dict[str, Any]]:
        with self._lock:
            result = self._sheet.values().get(
                spreadsheetId=self._spreadsheet_id, range=f"'{tab}'"
            ).execute()
        rows = result.get("values", [])
        if len(rows) < 2:
            return []
        headers = rows[0]
        return [dict(zip(headers, row + [""] * (len(headers) - len(row))))
                for row in rows[1:]]

    def _append(self, tab: str, headers: List[str], row: Dict[str, Any]) -> None:
        _assert_metadata_only(row)
        values = [str(row.get(h, "")) for h in headers]
        with self._lock:
            self._sheet.values().append(
                spreadsheetId=self._spreadsheet_id, range=f"'{tab}'!A1",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": [values]},
            ).execute()

    def ensure_schema(self) -> None:
        with self._lock:
            meta = self._svc.spreadsheets().get(spreadsheetId=self._spreadsheet_id).execute()
            existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
            for tab, headers in ((SHEET_EVENTS, EVENT_HEADERS), (SHEET_HEARTBEATS, HEARTBEAT_HEADERS)):
                if tab not in existing:
                    self._svc.spreadsheets().batchUpdate(
                        spreadsheetId=self._spreadsheet_id,
                        body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
                    ).execute()
                result = self._sheet.values().get(
                    spreadsheetId=self._spreadsheet_id, range=f"'{tab}'!A1:Z1"
                ).execute()
                current = result.get("values", [[]])
                if not current or not current[0]:
                    self._sheet.values().update(
                        spreadsheetId=self._spreadsheet_id, range=f"'{tab}'!A1",
                        valueInputOption="RAW", body={"values": [headers]},
                    ).execute()

    def store_event(self, row: Dict[str, Any]) -> None:
        row.setdefault("received_utc", _now_iso())
        self._append(SHEET_EVENTS, EVENT_HEADERS, row)

    def store_heartbeat(self, row: Dict[str, Any]) -> None:
        row.setdefault("received_utc", _now_iso())
        self._append(SHEET_HEARTBEATS, HEARTBEAT_HEADERS, row)

    def get_events(self, policy_id=None, user_id=None, limit=200):
        rows = self._read_all(SHEET_EVENTS)
        if policy_id:
            def _has(r):
                try:
                    return policy_id in {d.get("policy_id") for d in json.loads(r.get("detections_json", "[]"))}
                except (json.JSONDecodeError, TypeError):
                    return False
            rows = [r for r in rows if _has(r)]
        if user_id:
            rows = [r for r in rows if r.get("user_id") == user_id]
        return list(reversed(rows))[:limit]

    def get_heartbeats(self, limit=500):
        return list(reversed(self._read_all(SHEET_HEARTBEATS)))[:limit]
