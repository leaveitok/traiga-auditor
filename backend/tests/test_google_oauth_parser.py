"""
test_google_oauth_parser.py — the Google Workspace input path.

WHY THIS PATH EXISTS. A Google shop cannot run the Microsoft PowerShell export or the
Graph Explorer queries. Google's own equivalent is one no-code download: Admin console
-> Security -> API controls -> App access control -> "Accessed apps" -> Download list.
That CSV carries app name, client id, user count and granted scopes. We parse it
server-side into the SAME grant shape the Microsoft script produces, so the matcher,
scope classifier and merge path are reused unchanged.

These tests pin the parser contract: the exact export columns, scope-URL extraction from
the nested "Requested Services with Scopes" cell, integer user counts, a stripped BOM,
and the fail-secure rule that an unreadable row is COUNTED, never silently dropped.
"""
from engine.collectors import google_oauth

HEADER = ("App Name,Type,Id,Verification Status,Users,Org Unit,Access,"
          "Requested Services,Requested Services with Scopes,Ownership")

# A real-shaped row: OpenAI via Google Sign-in only (openid/email/profile).
ROW_OPENAI = (
    'OpenAI,Web Application,799-abc.apps.googleusercontent.com,Verified,200,,Configured,'
    '[Google Sign-in],'
    '"[Google Sign-in : [https://www.googleapis.com/auth/userinfo.email, '
    'https://www.googleapis.com/auth/userinfo.profile, openid]]",Third party'
)
# A high-reach row with multiple services and mail.google.com full access.
ROW_ZOOM = (
    'Zoom,Web Application,849-xyz.apps.googleusercontent.com,Verified,384,,Not configured,'
    '"[Drive, Gmail, Google Sign-in]",'
    '"[Drive : [https://www.googleapis.com/auth/drive] | '
    'Gmail : [https://mail.google.com/] | '
    'Google Sign-in : [https://www.googleapis.com/auth/userinfo.email, openid]]",Third party'
)
# Fail-secure case: a row whose App Name is blank must be counted, not silently dropped.
ROW_BLANK = ',Web Application,000-nil.apps.googleusercontent.com,Not verified,1,,Not configured,[],[],Unknown'


def _csv(*rows, header=HEADER, bom=False):
    text = header + "\n" + "\n".join(rows) + "\n"
    return ("﻿" + text) if bom else text


def test_header_is_recognised():
    grants, meta = google_oauth.parse_google_export(_csv(ROW_OPENAI))
    assert meta["header_ok"] is True
    assert meta["rows"] == 1 and meta["parsed"] == 1 and meta["unreadable_rows"] == 0


def test_grant_shape_and_provider():
    grants, _ = google_oauth.parse_google_export(_csv(ROW_OPENAI))
    g = grants[0]
    assert g["provider"] == "google"
    assert g["app_name"] == "OpenAI"
    assert g["app_id"] == "799-abc.apps.googleusercontent.com"
    assert g["user_count"] == 200            # integer, not string
    assert g["publisher"] == ""              # Google export has no publisher column
    # scopes pulled out of the nested "with Scopes" cell, including the bare openid token
    assert "https://www.googleapis.com/auth/userinfo.email" in g["scopes"]
    assert "openid" in g["scopes"]


def test_scope_extraction_across_services_including_full_mailbox():
    grants, _ = google_oauth.parse_google_export(_csv(ROW_ZOOM))
    scopes = grants[0]["scopes"]
    assert "https://www.googleapis.com/auth/drive" in scopes
    assert "https://mail.google.com/" in scopes          # full-mailbox scope captured
    assert "openid" in scopes


def test_blank_app_name_is_counted_not_dropped():
    """Fail-secure: a partially unreadable export must never look like a clean tenant."""
    grants, meta = google_oauth.parse_google_export(_csv(ROW_OPENAI, ROW_BLANK))
    assert meta["rows"] == 2
    assert meta["parsed"] == 1
    assert meta["unreadable_rows"] == 1
    assert all(g["app_name"] for g in grants)


def test_utf8_bom_is_stripped():
    grants, meta = google_oauth.parse_google_export(_csv(ROW_OPENAI, bom=True))
    assert meta["header_ok"] is True
    assert grants[0]["app_name"] == "OpenAI"


def test_non_google_csv_is_rejected_by_header():
    grants, meta = google_oauth.parse_google_export("foo,bar,baz\n1,2,3\n")
    assert meta["header_ok"] is False
