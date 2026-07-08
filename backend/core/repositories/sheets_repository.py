"""
sheets_repository.py — Google Sheets implementation of GovernanceRepository.

This is the ONLY file that knows about Google Sheets.
Routes, engines, and services never import this directly — they receive it
via FastAPI Depends(get_repository) wired in main.py.

To migrate to Firestore: implement GovernanceRepository Protocol in
firestore_repository.py, then change get_repository() in main.py.
This file stays untouched.

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
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from core import config

# TTL for read cache in seconds. Keeps the Sheets quota well under the
# 60 reads/min/user limit while the dashboard polls aggressively.
_READ_CACHE_TTL = 60  # seconds

try:
    import httplib2                                                    # type: ignore
    from google.oauth2 import service_account                         # type: ignore
    from googleapiclient.discovery import build                       # type: ignore
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False

# Try to import the httplib2 transport for AuthorizedHttp (optional extra in google-auth).
# If unavailable we fall back to passing credentials= directly (no hard timeout).
try:
    from google.auth.transport.httplib2 import AuthorizedHttp as _AuthorizedHttp  # type: ignore
    _HTTPLIB2_TRANSPORT = True
except ImportError:
    _HTTPLIB2_TRANSPORT = False

# Hard timeout for every Sheets API call.
# Without this, hung connections block uvicorn indefinitely.
_SHEETS_TIMEOUT_SECONDS = 20

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS: Dict[str, List[str]] = {
    config.SHEET_TARGETS: [
        "id", "city", "jurisdiction", "domain", "url", "tags", "added_utc", "active",
        "cloudflare_protected",
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
    config.SHEET_USERS: [
        "email", "role", "city", "created_utc", "agency_id", "cities",
    ],
    "AIAssets": [
        "asset_key", "city", "vendor_id", "display_name", "asset_types_json",
        "provenance", "lifecycle_status", "presence",
        "first_observed_utc", "last_observed_utc",
        "page_url", "match_confidence", "evidence_json",
        "owner_email", "owner_name",
        "attested_by", "attested_utc", "attestation_note",
        "department", "purpose", "data_categories_json", "next_review_utc",
    ],
    "Agencies": [
        "id", "name", "granted_cities", "created_utc",
    ],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SheetsRepository:
    """
    Google Sheets implementation of GovernanceRepository Protocol.
    Satisfies the Protocol via structural subtyping — no explicit inheritance.
    """

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
        if _HTTPLIB2_TRANSPORT:
            # Preferred: hard socket timeout prevents hung connections from
            # blocking uvicorn indefinitely (e.g. on 429 retry / dropped keep-alive).
            _http = _AuthorizedHttp(creds, http=httplib2.Http(timeout=_SHEETS_TIMEOUT_SECONDS))
            self._svc = build("sheets", "v4", http=_http, cache_discovery=False)
        else:
            # Fallback: no hard timeout, but the cache still reduces call frequency.
            self._svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._sheet = self._svc.spreadsheets()
        # In-memory TTL cache: tab_name → (expires_at, data)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        # httplib2 is not thread-safe — serialize all Sheets API calls
        self._api_lock = threading.RLock()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _range(self, tab: str, cell_range: str = "") -> str:
        return f"'{tab}'!{cell_range}" if cell_range else f"'{tab}'"

    def _execute(self, request: Any) -> Any:
        """Thread-safe execute: serializes all Sheets API calls via RLock.
        httplib2.Http is not thread-safe; without this lock concurrent requests
        corrupt the shared connection and hang indefinitely."""
        with self._api_lock:
            return request.execute()

    def _read_all_raw(self, tab: str) -> List[Dict[str, Any]]:
        result = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab),
        ))
        rows = result.get("values", [])
        if len(rows) < 2:
            return []
        headers = rows[0]
        return [dict(zip(headers, row + [""] * (len(headers) - len(row))))
                for row in rows[1:]]

    def _cached_read(self, tab: str, ttl: int = _READ_CACHE_TTL) -> List[Dict[str, Any]]:
        """Return cached tab data if fresh; otherwise fetch and cache."""
        entry = self._cache.get(tab)
        if entry and time.monotonic() < entry[0]:
            return entry[1]
        data = self._read_all_raw(tab)
        self._cache[tab] = (time.monotonic() + ttl, data)
        return data

    def _invalidate(self, *tabs: str) -> None:
        """Evict one or more tabs from the cache (called after writes)."""
        for tab in tabs:
            self._cache.pop(tab, None)

    def _append_row(self, tab: str, row_dict: Dict[str, Any]) -> None:
        headers = HEADERS[tab]
        values = [str(row_dict.get(h, "")) for h in headers]
        self._execute(self._sheet.values().append(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab, "A1"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [values]},
        ))

    def _upsert_by_key(self, tab: str, key_field: str,
                       key_value: str, row_dict: Dict[str, Any]) -> None:
        result = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab),
        ))
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
            self._execute(self._sheet.values().update(
                spreadsheetId=config.SPREADSHEET_ID,
                range=self._range(tab, f"A{target_row_idx}"),
                valueInputOption="RAW",
                body={"values": [values]},
            ))
        else:
            self._append_row(tab, row_dict)

    def _existing_sheet_titles(self) -> List[str]:
        meta = self._execute(self._svc.spreadsheets().get(
            spreadsheetId=config.SPREADSHEET_ID
        ))
        return [s["properties"]["title"] for s in meta.get("sheets", [])]

    def _create_tab(self, title: str) -> None:
        self._execute(self._svc.spreadsheets().batchUpdate(
            spreadsheetId=config.SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ))

    # ── GovernanceRepository Protocol implementation ──────────────────────────

    def ensure_schema(self) -> None:
        """Create missing tabs and write header rows if absent."""
        existing = self._existing_sheet_titles()
        for tab, headers in HEADERS.items():
            if tab not in existing:
                self._create_tab(tab)
            result = self._execute(self._sheet.values().get(
                spreadsheetId=config.SPREADSHEET_ID,
                range=self._range(tab, "A1:Z1"),
            ))
            current = result.get("values", [[]])
            if not current or not current[0]:
                self._execute(self._sheet.values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=self._range(tab, "A1"),
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ))

    def get_targets(self) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        rows = self._cached_read(config.SHEET_TARGETS)
        result = [r for r in rows if r.get("active", "true").lower() != "false"]
        for r in result:
            # Normalise cloudflare_protected to bool — may be absent in older sheets
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
        self._invalidate(config.SHEET_TARGETS)
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
        self._append_row(config.SHEET_TARGETS, row)
        # Return with bool-typed cloudflare_protected (consistent with get_targets)
        return {**row, "cloudflare_protected": cloudflare_protected, "active": True}  # type: ignore[arg-type]

    def deactivate_target(self, target_id: str) -> bool:
        self._invalidate(config.SHEET_TARGETS)
        # TODO: enforce admin-only write permission (auth placeholder)
        result = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(config.SHEET_TARGETS),
        ))
        rows = result.get("values", [])
        if not rows:
            return False
        headers = rows[0]
        id_col     = headers.index("id")     if "id"     in headers else -1
        active_col = headers.index("active") if "active" in headers else -1
        for i, row in enumerate(rows[1:], start=2):
            if id_col >= 0 and len(row) > id_col and row[id_col] == target_id:
                if active_col >= 0:
                    col_letter = chr(ord("A") + active_col)
                    self._execute(self._sheet.values().update(
                        spreadsheetId=config.SPREADSHEET_ID,
                        range=self._range(config.SHEET_TARGETS, f"{col_letter}{i}"),
                        valueInputOption="RAW",
                        body={"values": [["false"]]},
                    ))
                    return True
        return False

    def update_target(self, target_id: str, fields: Dict[str, Any]) -> bool:
        """Update mutable scan settings; per-column writes, same pattern as deactivate."""
        self._invalidate(config.SHEET_TARGETS)
        result = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(config.SHEET_TARGETS),
        ))
        rows = result.get("values", [])
        if not rows:
            return False
        headers = rows[0]
        id_col = headers.index("id") if "id" in headers else -1
        # column name -> string value (Sheets contract: everything is a string)
        col_values: Dict[str, str] = {}
        if "cloudflare_protected" in fields:
            col_values["cloudflare_protected"] = str(bool(fields["cloudflare_protected"])).lower()
        if "tags" in fields:
            col_values["tags"] = json.dumps(list(fields["tags"]))
        if "url" in fields and str(fields["url"]).strip():
            col_values["url"] = str(fields["url"]).strip()
        if not col_values:
            return True
        for i, row in enumerate(rows[1:], start=2):
            if id_col >= 0 and len(row) > id_col and row[id_col] == target_id:
                for col_name, value in col_values.items():
                    if col_name not in headers:
                        continue
                    col_letter = chr(ord("A") + headers.index(col_name))
                    self._execute(self._sheet.values().update(
                        spreadsheetId=config.SPREADSHEET_ID,
                        range=self._range(config.SHEET_TARGETS, f"{col_letter}{i}"),
                        valueInputOption="RAW",
                        body={"values": [[value]]},
                    ))
                return True
        return False

    # ── Safe Harbor (Municipal AI Profile attestations) ─────────────────────

    def get_safe_harbor(self, city: str) -> List[Dict[str, Any]]:
        rows = self._cached_read("SafeHarbor", ttl=60)
        return [r for r in rows
                if str(r.get("city", "")).lower() == city.lower()]

    def upsert_safe_harbor(self, record: Dict[str, Any]) -> Dict[str, Any]:
        city = str(record.get("city", "")).strip()
        control_id = str(record.get("control_id", "")).strip()
        if not city or not control_id:
            raise ValueError("city and control_id are required")
        self._invalidate("SafeHarbor")
        key = f"{city}|{control_id}"
        self._upsert_by_key("SafeHarbor", "record_key", key,
                            {"record_key": key,
                             **{k: str(v) for k, v in record.items()}})
        return record

    def get_scorecard(self) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        return self._cached_read(config.SHEET_SCORECARD)

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
        """Remove the scorecard row for the given city. Returns True if deleted."""
        self._invalidate(config.SHEET_SCORECARD)
        result = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(config.SHEET_SCORECARD),
        ))
        rows = result.get("values", [])
        if not rows:
            return False
        headers = rows[0]
        city_col = headers.index("city") if "city" in headers else -1
        for i, row in enumerate(rows[1:], start=2):
            if city_col >= 0 and len(row) > city_col and row[city_col] == city:
                blank = [""] * len(headers)
                self._execute(self._sheet.values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=self._range(config.SHEET_SCORECARD, f"A{i}"),
                    valueInputOption="RAW",
                    body={"values": [blank]},
                ))
                return True
        return False

    def write_scorecard_rows(self, rows: List[Dict[str, Any]]) -> None:
        self._invalidate(config.SHEET_SCORECARD)
        # TODO: enforce system-level write only (auth placeholder)
        for row in rows:
            self._upsert_by_key(
                config.SHEET_SCORECARD, "city", row["city"],
                {
                    "city":                 row["city"],
                    "jurisdiction":         row.get("jurisdiction", ""),
                    "domain":               row.get("domain", ""),
                    "ai_assets_json":       json.dumps(row.get("ai_assets_detected", [])),
                    "traiga_status":        row.get("traiga_status", "not_assessed"),
                    "open_violations_count": len(row.get("open_violations", [])),
                    "min_days_remaining":   row.get("min_days_remaining", ""),
                    "compliance_score":     row.get("compliance_score", 100),
                    "band":                 row.get("band", "green"),
                    "last_scanned_utc":     row.get("last_scanned_utc", _now_iso()),
                }
            )

    def get_violations(self, status: Optional[str] = None,
                       city: Optional[str] = None) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        rows = self._cached_read(config.SHEET_VIOLATIONS)
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if city:
            rows = [r for r in rows if r.get("city", "").lower() == city.lower()]
        return rows

    def write_violations(self, violations: List[Dict[str, Any]]) -> None:
        self._invalidate(config.SHEET_VIOLATIONS)
        # TODO: enforce system-level write only (auth placeholder)
        for v in violations:
            self._upsert_by_key(
                config.SHEET_VIOLATIONS, "violation_id", v["violation_id"],
                {
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
            )

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        # TODO: scope to requesting user's jurisdiction (auth placeholder)
        rows = self._cached_read(config.SHEET_AUDIT_LOG, ttl=30)
        return list(reversed(rows))[:limit]

    def append_audit_log(self, event: str, city_count: int,
                         failures: int, details: Dict[str, Any]) -> None:
        self._append_row(config.SHEET_AUDIT_LOG, {
            "timestamp_utc": _now_iso(),
            "event":         event,
            "city_count":    city_count,
            "failures":      failures,
            "details_json":  json.dumps(details),
        })

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        """Return the LATEST user row for the given email, or None."""
        rows = self._cached_read(config.SHEET_USERS, ttl=120)
        match = None
        for row in rows:
            if row.get("email", "").lower() == email.lower():
                match = row      # keep scanning; last write wins
        return match

    def delete_user(self, email: str) -> bool:
        """Blank out every row for this email. Returns True if any removed."""
        self._invalidate(config.SHEET_USERS)
        result = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(config.SHEET_USERS)))
        rows = result.get("values", [])
        if not rows:
            return False
        headers = rows[0]
        email_col = headers.index("email") if "email" in headers else 0
        removed = False
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > email_col and row[email_col].lower() == email.lower():
                self._execute(self._sheet.values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=self._range(config.SHEET_USERS, f"A{i}"),
                    valueInputOption="RAW",
                    body={"values": [[""] * len(headers)]}))
                removed = True
        return removed

    # ── Agencies ──────────────────────────────────────────────────────────────

    def get_agencies(self) -> List[Dict[str, Any]]:
        return list(self._cached_read("Agencies", ttl=120))

    def get_agency(self, agency_id: str) -> Optional[Dict[str, Any]]:
        for a in self._cached_read("Agencies", ttl=120):
            if a.get("id") == agency_id:
                return a
        return None

    def upsert_agency(self, agency_id: Optional[str], name: str,
                      granted_cities: List[str]) -> Dict[str, Any]:
        self._invalidate("Agencies")
        aid = agency_id or str(uuid.uuid4())[:8]
        row = {
            "id": aid, "name": name,
            "granted_cities": json.dumps(list(granted_cities)),
            "created_utc": _now_iso(),
        }
        self._upsert_by_key("Agencies", "id", aid, row)
        return {**row, "granted_cities": list(granted_cities)}

    # ── AI Use-Case Inventory ─────────────────────────────────────────────────

    def get_ai_assets(self, city: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self._cached_read("AIAssets", ttl=60)
        if city:
            rows = [r for r in rows if r.get("city") == city]
        return list(rows)

    def upsert_ai_asset(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        """Merge-preserving upsert keyed by asset_key (see Protocol contract)."""
        key = asset.get("asset_key", "")
        if not key:
            raise ValueError("asset_key is required")
        self._invalidate("AIAssets")
        existing = next((r for r in self._read_all_raw_dicts("AIAssets")
                         if r.get("asset_key") == key), {})
        merged = {**existing, **{k: v for k, v in asset.items() if v is not None}}
        self._upsert_by_key("AIAssets", "asset_key", key,
                            {k: str(v) for k, v in merged.items()})
        return merged

    def _read_all_raw_dicts(self, tab: str) -> List[Dict[str, Any]]:
        """Uncached dict read (upsert must merge against fresh data)."""
        rows = self._execute(self._sheet.values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=self._range(tab),
        )).get("values", [])
        if len(rows) < 2:
            return []
        headers = rows[0]
        return [dict(zip(headers, r + [""] * (len(headers) - len(r))))
                for r in rows[1:]]

    def upsert_user(self, email: str, role: str, city: Optional[str] = None,
                    agency_id: Optional[str] = None,
                    cities: Optional[List[str]] = None) -> None:
        self._invalidate(config.SHEET_USERS)
        city_list = list(cities) if cities is not None else ([city] if city else [])
        # Latest row wins on lookup (get_user scans and the reader takes the
        # last match); append a fresh fully-populated row.
        self._append_row(config.SHEET_USERS, {
            "email": email, "role": role,
            "city": (city_list[0] if city_list else ""),
            "agency_id": agency_id or "",
            "cities": json.dumps(city_list),
            "created_utc": _now_iso(),
        })
        return

    def _legacy_upsert_user(self, email: str, role: str, city: Optional[str]) -> None:
        # (retained for reference; superseded by the append-latest-wins upsert)
        self._invalidate(config.SHEET_USERS)
        rows = self._read_all_raw(config.SHEET_USERS)
        if not rows:
            self._append_row(config.SHEET_USERS, {
                "email": email, "role": role,
                "city": city or "", "created_utc": _now_iso(),
            })
            return
        headers = rows[0]
        email_idx = headers.index("email") if "email" in headers else 0
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > email_idx and row[email_idx].lower() == email.lower():
                role_idx = headers.index("role") if "role" in headers else 1
                city_idx = headers.index("city") if "city" in headers else 2
                self._execute(self._sheet.values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=self._range(config.SHEET_USERS, f"A{i}:Z{i}"),
                    valueInputOption="RAW",
                    body={"values": [
                        [row[j] if j < len(row) else "" for j in range(max(city_idx + 1, len(row)))]
                    ]},
                ))
                # Simpler: just append a new row (last entry wins on lookup)
                self._append_row(config.SHEET_USERS, {
                    "email": email, "role": role,
                    "city": city or "", "created_utc": _now_iso(),
                })
                return
        self._append_row(config.SHEET_USERS, {
            "email": email, "role": role,
            "city": city or "", "created_utc": _now_iso(),
        })

    def get_users(self) -> List[Dict[str, Any]]:
        # TODO: enforce admin-only read permission (auth placeholder)
        return list(self._cached_read(config.SHEET_USERS, ttl=120))
