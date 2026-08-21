"""
google_oauth.py — parse a Google Workspace OAuth app export into provider-agnostic
grant records.

PURE: text in, grant dicts out. No I/O, no network, no repository. The dicts match
the shape engine.collectors.oauth.normalize expects (identical to what the Microsoft
export script produces), so the Google channel reuses the whole matcher, scope
classifier, and merge path with zero changes.

Source: Google Admin console -> Security -> Access and data control -> API controls
-> Manage App Access -> "Accessed apps" -> Download list. That CSV has columns:
  App Name, Type, Id, Verification Status, Users, Org Unit, Access,
  Requested Services, Requested Services with Scopes, Ownership
We read App Name, Id (the OAuth client_id), Users (count), and pull the granted scope
URLs out of "Requested Services with Scopes". Google's export carries no publisher
column, so publisher is left blank and matching relies on the app display name.

Fail-secure: a row we cannot read is COUNTED (unreadable_rows), never silently
dropped -- an export that partially fails to parse must never look like a clean tenant.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Tuple

PROVIDER = "google"

# A Google OAuth scope is a full URL (https://www.googleapis.com/auth/..., or
# https://mail.google.com/), plus the bare "openid" token. Stop a URL at whitespace,
# comma or a closing bracket -- the export wraps scope lists in [ ... ] separated by
# ", " and services by " | ".
_SCOPE_RE = re.compile(r"https?://[^\s,\]]+|openid")

_C_NAME = "App Name"
_C_ID = "Id"
_C_USERS = "Users"
_C_SCOPES = "Requested Services with Scopes"
_C_TYPE = "Type"
_C_VERIF = "Verification Status"
_C_ACCESS = "Access"
_C_OWNER = "Ownership"


def _to_int(v: Any) -> Any:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_google_export(csv_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parse the Accessed-apps CSV into (grants, meta).

    Each grant:
      {app_id, app_name, publisher, provider, scopes[], user_count,
       google_type, google_verification, google_access, google_ownership}
    meta:
      {rows, parsed, unreadable_rows, header_ok}
    """
    text = (csv_text or "").lstrip("﻿")  # strip a UTF-8 BOM if present
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    header_ok = _C_NAME in fields and _C_ID in fields

    grants: List[Dict[str, Any]] = []
    unreadable = 0
    total = 0
    for row in reader:
        total += 1
        try:
            name = (row.get(_C_NAME) or "").strip()
            if not name:
                unreadable += 1
                continue
            scopes = _SCOPE_RE.findall(row.get(_C_SCOPES) or "")
            grants.append({
                "app_id":     (row.get(_C_ID) or "").strip(),
                "app_name":   name,
                "publisher":  "",
                "provider":   PROVIDER,
                "scopes":     scopes,
                "user_count": _to_int(row.get(_C_USERS)),
                # Google-only evidence -- ignored by the matcher, available downstream:
                "google_type":         (row.get(_C_TYPE) or "").strip(),
                "google_verification": (row.get(_C_VERIF) or "").strip(),
                "google_access":       (row.get(_C_ACCESS) or "").strip(),
                "google_ownership":    (row.get(_C_OWNER) or "").strip(),
            })
        except Exception:
            unreadable += 1

    meta = {"rows": total, "parsed": len(grants),
            "unreadable_rows": unreadable, "header_ok": header_ok}
    return grants, meta
