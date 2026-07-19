"""
test_oauth_discovery.py — PURE OAuth / shadow-AI normalizer (no network, no credentials).

Phase 0 of the OAuth channel: proves the matching, the scope classification, and — most
importantly — the PRIVACY default, before any tenant is ever contacted. Fixtures are
synthetic but shaped like real Microsoft Graph oauth2PermissionGrants / Google token records.
"""
import json
import os

from engine.collectors import identity, oauth

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "SCHEMA_DEFINITION.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    SCHEMA = json.load(_f)
INDEX = identity.build_tool_index(SCHEMA)
RULES = SCHEMA["OAuth_Scope_Sensitivity"]

# --- scope classification (pure) ------------------------------------------------

def test_mailbox_scope_is_high():
    r = oauth.classify_scopes(["Mail.Read", "openid"], RULES)
    assert r["sensitivity"] == "high"
    assert any("mailbox" in x for x in r["reaches"])


def test_google_drive_url_scope_is_high():
    r = oauth.classify_scopes(["https://www.googleapis.com/auth/drive.readonly"], RULES)
    assert r["sensitivity"] == "high"


def test_signin_only_scopes_are_low():
    r = oauth.classify_scopes(["openid", "profile", "email", "offline_access"], RULES)
    assert r["sensitivity"] == "low" and r["write"] is False


def test_write_capability_escalates_tier():
    read = oauth.classify_scopes(["Calendars.Read"], RULES)
    write = oauth.classify_scopes(["Calendars.ReadWrite"], RULES)
    assert read["sensitivity"] == "medium"
    assert write["write"] is True and write["sensitivity"] == "high"


def test_unknown_scope_is_unknown_not_guessed():
    r = oauth.classify_scopes(["Some.Vendor.Custom.Thing"], RULES)
    assert r["sensitivity"] == "unknown" and r["reaches"] == []


# --- normalization / matching ---------------------------------------------------

def _grant(name, scopes, users=None, **kw):
    g = {"app_id": kw.get("app_id", "00000000-app"), "app_name": name,
         "publisher": kw.get("publisher", "Example Publisher"),
         "provider": kw.get("provider", "microsoft"), "scopes": scopes,
         "first_seen": "2026-07-01", "last_seen": "2026-07-18"}
    if users is not None:
        g["users"] = users
    if "user_count" in kw:
        g["user_count"] = kw["user_count"]
    return g


def test_known_ai_tool_is_surfaced():
    grants = [_grant("ChatGPT", ["openid", "Mail.Read"], users=["a@x.gov", "b@x.gov"])]
    res = oauth.normalize(grants, INDEX, "City of Testville", scope_rules=RULES)
    assert res["source_meta"]["rows"] == 1
    assert (res["source_meta"]["matched"] + res["source_meta"]["candidates"]) >= 1


def test_non_ai_app_is_not_invented_as_ai():
    grants = [_grant("Payroll Timesheet Sync", ["Calendars.Read"])]
    res = oauth.normalize(grants, INDEX, "City of Testville", scope_rules=RULES)
    assert res["source_meta"]["matched"] == 0
    assert res["source_meta"]["candidates"] == 0


def test_user_identities_are_dropped_by_default():
    """PRIVACY DEFAULT: employee identities must never leave the pure layer unasked."""
    grants = [_grant("ChatGPT", ["openid"], users=["alice@city.gov", "bob@city.gov"])]
    res = oauth.normalize(grants, INDEX, "City of Testville", scope_rules=RULES)
    blob = json.dumps(res)
    assert "alice@city.gov" not in blob and "bob@city.gov" not in blob
    assert "consenting_users" not in blob


def test_user_identities_only_on_explicit_opt_in():
    grants = [_grant("ChatGPT", ["openid"], users=["alice@city.gov"])]
    res = oauth.normalize(grants, INDEX, "City of Testville", scope_rules=RULES,
                          include_users=True)
    assert "alice@city.gov" in json.dumps(res)


def test_user_count_survives_without_identities():
    grants = [_grant("ChatGPT", ["openid"], users=["a@x.gov", "b@x.gov", "c@x.gov"])]
    res = oauth.normalize(grants, INDEX, "City of Testville", scope_rules=RULES)
    blob = json.dumps(res)
    assert "@x.gov" not in blob
    assert "3" in blob   # the count is retained as evidence


def test_provenance_is_oauth():
    assert oauth.PROVENANCE == "discovered_oauth"
