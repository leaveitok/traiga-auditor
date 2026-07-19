"""
test_oauth_orchestrator.py — the SAFETY properties of the OAuth orchestrator.

Phase 1 runs against a real municipal tenant, so the guarantees that matter are not
"does it match" (covered in test_oauth_discovery.py) but "can it surprise the customer":
dry run writes NOTHING, an empty export is never read as "this city is clean", the flag
gates it off, tenancy is fail-secure, and every run is audit-logged.
"""
import json

from core.discovery import oauth_source
from tests.mock_repository import MockGovernanceRepository


def _repo(enabled=True):
    """A repo with the channel flag set through the REAL settings path.

    Deliberately NOT monkeypatching core.settings.get_bool: a module-level patch leaks
    into every later test in the same process (it broke test_settings when this file was
    first written). Persist the setting instead, so the orchestrator exercises the same
    code path production does.
    """
    repo = MockGovernanceRepository()
    import core.settings as settings
    settings.save(repo, {"OAUTH_DISCOVERY_ENABLED": bool(enabled)}, actor="test")
    return repo


def _grants():
    return [
        {"app_id": "a-1", "app_name": "ChatGPT", "publisher": "OpenAI",
         "provider": "microsoft", "scopes": ["openid", "Mail.Read"], "user_count": 4},
        {"app_id": "a-2", "app_name": "Payroll Timesheet Sync", "publisher": "Acme",
         "provider": "microsoft", "scopes": ["Calendars.Read"], "user_count": 2},
    ]


def test_dry_run_writes_nothing():
    repo = _repo()
    before = len(repo.get_ai_assets())
    out = oauth_source.run_oauth_discovery(repo, "City of Testville", _grants(), dry_run=True)
    assert out["dry_run"] is True
    assert out["written"] == 0
    assert len(repo.get_ai_assets()) == before, "dry run must not persist anything"
    # It still REPORTS what it found, otherwise the pilot learns nothing.
    assert out["rows"] == 2


def test_real_run_writes():
    repo = _repo()
    out = oauth_source.run_oauth_discovery(repo, "City of Testville", _grants(), dry_run=False)
    assert out["dry_run"] is False
    assert out["written"] >= 1
    assert len(repo.get_ai_assets()) >= 1


def test_empty_export_is_not_a_clean_bill():
    """Fail-secure: no records means 'we learned nothing', never 'no AI here'."""
    repo = _repo()
    out = oauth_source.run_oauth_discovery(repo, "City of Testville", [], dry_run=False)
    assert out["written"] == 0
    assert out["rows"] == 0
    assert "no_grants_supplied" in out["errors"]
    assert len(repo.get_ai_assets()) == 0


def test_disabled_flag_blocks_the_channel():
    repo = _repo(enabled=False)
    out = oauth_source.run_oauth_discovery(repo, "City of Testville", _grants(), dry_run=False)
    assert out["errors"] == ["oauth_discovery_disabled"]
    assert out["written"] == 0


def test_tenancy_is_fail_secure():
    repo = _repo()
    out = oauth_source.run_oauth_discovery(
        repo, "City of Elsewhere", _grants(), dry_run=False,
        allowed_cities={"City of Testville"})
    assert out["errors"] == ["city_out_of_scope"]
    assert out["written"] == 0


def test_every_run_is_audit_logged_including_dry_runs():
    repo = _repo()
    oauth_source.run_oauth_discovery(repo, "City of Testville", _grants(), dry_run=True,
                                     actor="cio@city.gov")
    logs = [l for l in repo.get_audit_log() if l.get("event") == "discovery_oauth"]
    assert logs, "a dry run still touches tenant data and must be logged"
    d = logs[-1].get("details", {})
    assert d.get("dry_run") is True
    assert d.get("actor") == "cio@city.gov"


def test_identities_not_persisted_by_default():
    repo = _repo()
    grants = [{"app_id": "a-1", "app_name": "ChatGPT", "provider": "microsoft",
               "scopes": ["openid"], "users": ["alice@city.gov", "bob@city.gov"]}]
    oauth_source.run_oauth_discovery(repo, "City of Testville", grants, dry_run=False)
    blob = json.dumps(repo.get_ai_assets())
    assert "alice@city.gov" not in blob and "bob@city.gov" not in blob
