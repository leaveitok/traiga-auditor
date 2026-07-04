"""
sheets.py — Google Sheets client (4-sheet schema).

Sheet layout
────────────
Targets    : id | city | jurisdiction | domain | url | tags | added_utc | active
Scorecard  : city | jurisdiction | domain | ai_assets_json | traiga_status |
             open_violations_count | min_days_remaining | compliance_score |
             band | last_scanned_utc
Violations : violation_id | city | domain | asset_id | vendor_id | rule_id |
             citation | severity | first_observed_utc | cure_deadline_utc |
             last_observed_utc | days_remaining | cure_period_status | status |
             evidence_json | needs_human_review | cured_utc
AuditLog   : timestamp_utc | event | city_count | failures | details_json

All reads/writes go through the SheetsClient singleton.  The service-account
key file path and spreadsheet ID come from core.config (env vars).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config

# Google API client is an optional dependency at import time; will raise a
# clear error only when you actually try to use SheetsClient.
try:
    from google.oauth2 import service_account            # type: ignore
    from googleapiclient.discovery import build          # type: ignore
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Header definitions (order matters — matches sheet column order) ───────────
HEADERS: Dict[str, List[str]] = {
    config.SHEET_TARGETS: [
        "id", "city", "jurisdiction", "domain", "url", "tags", "added_utc", "active"
    ],
    config.SHEET_SCORECARD: [
        "city", "jurisdiction", "domain", "ai_assets_json", "traiga_status",
        "open_violations_count", "min_days_remaining", "compliance_score",
        "band", "last_scanned_utc",
    ],
    config.SHEET_VIOLATIONS: [
        "violation_id", "city", "domain", "asset_id", "vendor_id", "rule_id",
        "citation", "severity", "first_observed_utc", "cure_deadline_utc",
        "last_observed_utc", "days_remaining", "cure_period_status", "status",
        "evidence_json", "needs_human_review", "cured_utc",
    ],
    config.SHEET_AUDIT_LOG: [
        "timestamp_utc", "event", "city_count", "failures", "details_json"
    ],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SheetsClient:
    """Thin wrapper around the Google Sheets API v4."""

    def __init__(self) -> None:
        if not _GOOGLE_AVAILABLE:
            raise RuntimeError(
                "google-api-python-client is not installed. "
                "Run: pip install google-api-python-client google-auth"
            )
        if not config.SPREADSHEET_ID:
            raise RuntimeError(
                "SPREADSHEET_ID env var is not set. "
                "Copy the ID from your Google Sheets URL."
            )
        creds = service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        self._svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._sheet = self._svc.spreadsheets()

    # ── generic helpers ───────────────────────────────────────────────────────

    def _range(self, tab: str, cell_range: str = "") -> str:
        return f"'{tab}'!{cell_range}" if cell_range else f"'{tab}'"

    def read_all(self, tab: str) -> List[Dict[str, Any]]:
        """Return all data rows as list-of-dicts (skips header row)."""
        result = self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab),
        ).execute()
        rows = result.get("values", [])
        if len(rows) < 2:
            return []
        headers = rows[0]
        return [dict(zip(headers, row + [""] * (len(headers) - len(row))))
                for row in rows[1:]]

    def append_row(self, tab: str, row_dict: Dict[str, Any]) -> None:
        """Append one row to a sheet using the defined header order."""
        headers = HEADERS[tab]
        values = [str(row_dict.get(h, "")) for h in headers]
        self._sheet.values().append(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab, "A1"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [values]},
        ).execute()

    def upsert_by_key(self, tab: str, key_field: str,
                      key_value: str, row_dict: Dict[str, Any]) -> None:
        """Update a row whose key_field == key_value, or append if not found."""
        result = self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab),
        ).execute()
        rows = result.get("values", [])
        headers = rows[0] if rows else HEADERS[tab]
        key_col = headers.index(key_field) if key_field in headers else -1
        target_row_idx = None
        for i, row in enumerate(rows[1:], start=2):
            if key_col >= 0 and len(row) > key_col and row[key_col] == key_value:
                target_row_idx = i
                break

        values = [str(row_dict.get(h, "")) for h in headers]
        if target_row_idx:
            self._sheet.values().update(
                spreadsheetId=config.SPREADSHEET_ID,
                range=self._range(tab, f"A{target_row_idx}"),
                valueInputOption="RAW",
                body={"values": [values]},
            ).execute()
        else:
            self.append_row(tab, row_dict)

    def _existing_sheet_titles(self) -> List[str]:
        """Return the titles of all tabs currently in the spreadsheet."""
        meta = self._svc.spreadsheets().get(
            spreadsheetId=config.SPREADSHEET_ID
        ).execute()
        return [s["properties"]["title"] for s in meta.get("sheets", [])]

    def _create_tab(self, title: str) -> None:
        """Add a new tab (sheet) to the spreadsheet."""
        self._svc.spreadsheets().batchUpdate(
            spreadsheetId=config.SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()

    def ensure_headers(self) -> None:
        """Create missing tabs and write header rows if the first row is empty."""
        existing = self._existing_sheet_titles()
        for tab, headers in HEADERS.items():
            # Create the tab if it doesn't exist
            if tab not in existing:
                self._create_tab(tab)
            # Write headers if row 1 is empty
            result = self._sheet.values().get(
                spreadsheetId=config.SPREADSHEET_ID,
                range=self._range(tab, "A1:Z1"),
            ).execute()
            current = result.get("values", [[]])
            if not current or not current[0]:
                self._sheet.values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=self._range(tab, "A1"),
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ).execute()

    # ── domain-specific helpers ───────────────────────────────────────────────

    def get_targets(self) -> List[Dict[str, Any]]:
        rows = self.read_all(config.SHEET_TARGETS)
        return [r for r in rows if r.get("active", "true").lower() != "false"]

    def add_target(self, city: str, jurisdiction: str, domain: str,
                   url: str, tags: List[str]) -> Dict[str, Any]:
        import uuid
        row = {
            "id": str(uuid.uuid4())[:8],
            "city": city,
            "jurisdiction": jurisdiction,
            "domain": domain,
            "url": url,
            "tags": json.dumps(tags),
            "added_utc": _now_iso(),
            "active": "true",
        }
        self.append_row(config.SHEET_TARGETS, row)
        return row

    def deactivate_target(self, target_id: str) -> bool:
        result = self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(config.SHEET_TARGETS),
        ).execute()
        rows = result.get("values", [])
        if not rows:
            return False
        headers = rows[0]
        id_col = headers.index("id") if "id" in headers else -1
        active_col = headers.index("active") if "active" in headers else -1
        for i, row in enumerate(rows[1:], start=2):
            if id_col >= 0 and len(row) > id_col and row[id_col] == target_id:
                if active_col >= 0:
                    col_letter = chr(ord("A") + active_col)
                    self._sheet.values().update(
                        spreadsheetId=config.SPREADSHEET_ID,
                        range=self._range(config.SHEET_TARGETS, f"{col_letter}{i}"),
                        valueInputOption="RAW",
                        body={"values": [["false"]]},
                    ).execute()
                    return True
        return False

    def write_scorecard_rows(self, rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            self.upsert_by_key(
                config.SHEET_SCORECARD, "city", row["city"],
                {
                    "city": row["city"],
                    "jurisdiction": row.get("jurisdiction", ""),
                    "domain": row.get("domain", ""),
                    "ai_assets_json": json.dumps(row.get("ai_assets_detected", [])),
                    "traiga_status": row.get("traiga_status", "not_assessed"),
                    "open_violations_count": len(row.get("open_violations", [])),
                    "min_days_remaining": row.get("min_days_remaining", ""),
                    "compliance_score": row.get("compliance_score", 100),
                    "band": row.get("band", "green"),
                    "last_scanned_utc": row.get("last_scanned_utc", _now_iso()),
                }
            )

    def write_violations(self, violations: List[Dict[str, Any]]) -> None:
        for v in violations:
            self.upsert_by_key(
                config.SHEET_VIOLATIONS, "violation_id", v["violation_id"],
                {
                    "violation_id": v["violation_id"],
                    "city": v.get("city", ""),
                    "domain": v.get("domain", ""),
                    "asset_id": v.get("asset_id", ""),
                    "vendor_id": v.get("vendor_id", ""),
                    "rule_id": v.get("rule_id", ""),
                    "citation": v.get("citation", ""),
                    "severity": v.get("severity", "medium"),
                    "first_observed_utc": v.get("first_observed_utc", ""),
                    "cure_deadline_utc": v.get("cure_deadline_utc", ""),
                    "last_observed_utc": v.get("last_observed_utc", ""),
                    "days_remaining": v.get("days_remaining", ""),
                    "cure_period_status": str(v.get("cure_period_status", True)),
                    "status": v.get("status", "in_cure"),
                    "evidence_json": json.dumps(v.get("evidence", {})),
                    "needs_human_review": str(v.get("needs_human_review", True)),
                    "cured_utc": v.get("cured_utc", ""),
                }
            )

    def append_audit_log(self, event: str, city_count: int,
                         failures: int, details: Dict[str, Any]) -> None:
        self.append_row(config.SHEET_AUDIT_LOG, {
            "timestamp_utc": _now_iso(),
            "event": event,
            "city_count": city_count,
            "failures": failures,
            "details_json": json.dumps(details),
        })

    def get_violations(self) -> List[Dict[str, Any]]:
        return self.read_all(config.SHEET_VIOLATIONS)

    def get_scorecard(self) -> List[Dict[str, Any]]:
        return self.read_all(config.SHEET_SCORECARD)

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.read_all(config.SHEET_AUDIT_LOG)
        return list(reversed(rows))[:limit]
