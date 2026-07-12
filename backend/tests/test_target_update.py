"""
test_target_update.py — unit tests for PATCH /api/targets/{id} (platform_admin only).

Same standalone pattern as test_bulk_import: route function called directly with
a stub repo (run with PYTHONPATH=backend/tests/shims when fastapi is absent).
Contract: platform_admin can edit cloudflare_protected/tags/url post-creation
(the capability gap found 2026-07-07 — the flag was only settable at creation,
so WAF cities discovered by the sweep could not be excluded from bulk scans).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _setup_admin_email(email="chris@test.gov"):
    from core import config
    config.ADMIN_EMAILS = [email]
    return email


class StubRepo:
    def __init__(self, targets=None):
        self.targets = targets or []
        self.log_events = []

    def update_target(self, target_id, fields):
        for t in self.targets:
            if t["id"] == target_id:
                t.update(fields)
                return True
        return False

    def append_audit_log(self, **kw):
        self.log_events.append(kw)

    def get_user(self, email):
        return None

    def get_agency(self, agency_id):
        return None


def _run_patch(repo, user_email, target_id, **kw):
    from api.routes.targets import update_target, TargetUpdate
    return update_target(
        target_id=target_id,
        body=TargetUpdate(**kw),
        repo=repo,
        user={"uid": "u1", "email": user_email, "role": None, "city": None},
    )


def test_admin_can_flag_waf_city():
    admin = _setup_admin_email()
    repo = StubRepo(targets=[{"id": "fw1", "city": "Fort Worth", "cloudflare_protected": False}])
    result = _run_patch(repo, admin, "fw1", cloudflare_protected=True)
    assert result["updated"] == ["cloudflare_protected"]
    assert repo.targets[0]["cloudflare_protected"] is True
    assert any(e.get("event") == "target_updated" for e in repo.log_events)


def test_non_admin_gets_403():
    from fastapi import HTTPException
    _setup_admin_email("chris@test.gov")
    repo = StubRepo(targets=[{"id": "fw1", "city": "Fort Worth", "cloudflare_protected": False}])
    try:
        _run_patch(repo, "viewer@denton.gov", "fw1", cloudflare_protected=True)
        raise AssertionError("expected 403")
    except HTTPException as exc:
        assert exc.status_code == 403
    assert repo.targets[0]["cloudflare_protected"] is False  # unchanged


def test_unknown_target_404_and_empty_patch_400():
    from fastapi import HTTPException
    admin = _setup_admin_email()
    repo = StubRepo()
    try:
        _run_patch(repo, admin, "nope", cloudflare_protected=True)
        raise AssertionError("expected 404")
    except HTTPException as exc:
        assert exc.status_code == 404
    try:
        _run_patch(repo, admin, "nope")
        raise AssertionError("expected 400")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_admin_can_edit_population_and_city_and_it_logs():
    """Population + identity fields are editable post-capture and every applied
    change is written to the audit log (the edit-with-audit-log requirement)."""
    admin = _setup_admin_email()
    repo = StubRepo(targets=[{"id": "od1", "city": "Odesa", "population": 0}])
    result = _run_patch(repo, admin, "od1", city="Odessa", population=114000)
    assert set(result["updated"]) == {"city", "population"}
    assert repo.targets[0]["city"] == "Odessa"
    assert repo.targets[0]["population"] == 114000
    ev = [e for e in repo.log_events if e.get("event") == "target_updated"]
    assert ev and ev[0]["details"]["actor"] == admin
