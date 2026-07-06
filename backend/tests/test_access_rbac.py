"""
test_access_rbac.py — multi-tenant scoping + delegated-administration bounds.

The security-critical guarantee: a user can only ever see or act on cities
within their grant, and an agency admin can never grant beyond their agency.
"""
import json
import pytest

from core.access import (
    AccessDenied, ROLE_AGENCY_ADMIN, ROLE_PLATFORM_ADMIN, ROLE_VIEWER,
    assert_can_manage_agency, assert_can_manage_user, filter_rows,
    resolve_principal, scope_requested_cities, visible_cities,
)


class FakeRepo:
    """In-memory governance repo double for RBAC tests."""
    def __init__(self, users=None, agencies=None):
        self._users = {u["email"].lower(): u for u in (users or [])}
        self._agencies = {a["id"]: a for a in (agencies or [])}
    def get_user(self, email):
        return self._users.get(email.lower())
    def get_agency(self, agency_id):
        return self._agencies.get(agency_id)


AG = {"id": "ag-lwv", "name": "Lewisville Agency",
      "granted_cities": json.dumps(["City of Lewisville", "City of Flower Mound"])}


def _repo():
    return FakeRepo(
        users=[
            {"email": "viewer@lwv.gov", "role": "viewer", "agency_id": "ag-lwv",
             "cities": json.dumps(["City of Lewisville"])},
            {"email": "agencyadmin@lwv.gov", "role": "agency_admin", "agency_id": "ag-lwv",
             "cities": "[]"},
        ],
        agencies=[AG])


# ── Bootstrap / platform admin ────────────────────────────────────────────────

def test_platform_admin_from_env_sees_all(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", ["boss@city.gov"])
    p = resolve_principal({"email": "boss@city.gov"}, _repo())
    assert p.is_platform_admin
    assert visible_cities(p) is None            # None == all
    assert p.can_see_city("Anywhere")


# ── Viewer scoping ────────────────────────────────────────────────────────────

def test_viewer_scoped_to_granted_city(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    p = resolve_principal({"email": "viewer@lwv.gov"}, _repo())
    assert p.role == ROLE_VIEWER
    assert p.cities == {"City of Lewisville"}
    assert p.can_see_city("City of Lewisville")
    assert not p.can_see_city("City of Flower Mound")   # granted to agency, not to this viewer
    assert not p.can_trigger_audit()


def test_viewer_grant_bounded_by_agency(monkeypatch):
    """A stale city grant beyond the agency's grant is dropped on resolution."""
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    repo = FakeRepo(
        users=[{"email": "v@lwv.gov", "role": "viewer", "agency_id": "ag-lwv",
                "cities": json.dumps(["City of Lewisville", "City of Dallas"])}],
        agencies=[AG])
    p = resolve_principal({"email": "v@lwv.gov"}, repo)
    assert p.cities == {"City of Lewisville"}   # Dallas not in agency grant -> removed


def test_filter_rows_hides_other_cities(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    p = resolve_principal({"email": "viewer@lwv.gov"}, _repo())
    rows = [{"city": "City of Lewisville", "x": 1},
            {"city": "City of Dallas", "x": 2}]
    assert filter_rows(rows, p) == [{"city": "City of Lewisville", "x": 1}]


# ── Agency admin ──────────────────────────────────────────────────────────────

def test_agency_admin_sees_all_agency_cities(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    p = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    assert p.role == ROLE_AGENCY_ADMIN
    assert p.cities == {"City of Lewisville", "City of Flower Mound"}
    assert p.can_trigger_audit()


# ── Selective audit scoping ───────────────────────────────────────────────────

def test_scope_requested_cities_intersects_with_grant(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    p = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    # asked for one in-grant + one out-of-grant -> only in-grant survives
    assert set(scope_requested_cities(
        ["City of Lewisville", "City of Dallas"], p)) == {"City of Lewisville"}
    # empty request -> all of the principal's cities
    assert set(scope_requested_cities(None, p)) == p.cities


def test_scope_requested_cities_platform_admin_passthrough(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", ["boss@city.gov"])
    p = resolve_principal({"email": "boss@city.gov"}, _repo())
    assert scope_requested_cities(None, p) == []          # [] => all targets
    assert scope_requested_cities(["City of X"], p) == ["City of X"]


# ── Delegated administration bounds ───────────────────────────────────────────

def test_agency_admin_cannot_grant_city_outside_agency(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    actor = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    with pytest.raises(AccessDenied):
        assert_can_manage_user(
            actor, target_email="new@lwv.gov", target_role="viewer",
            target_agency_id="ag-lwv",
            target_cities=["City of Dallas"], repo=_repo())   # Dallas not in grant


def test_agency_admin_cannot_touch_other_agency(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    actor = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    with pytest.raises(AccessDenied):
        assert_can_manage_user(
            actor, target_email="x@other.gov", target_role="viewer",
            target_agency_id="ag-other", target_cities=[], repo=_repo())


def test_agency_admin_cannot_create_platform_admin(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    actor = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    with pytest.raises(AccessDenied):
        assert_can_manage_user(
            actor, target_email="x@lwv.gov", target_role="platform_admin",
            target_agency_id="ag-lwv", target_cities=[], repo=_repo())


def test_agency_admin_valid_grant_succeeds(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    actor = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    # in-grant city, own agency, viewer role -> allowed (no raise)
    assert_can_manage_user(
        actor, target_email="new@lwv.gov", target_role="viewer",
        target_agency_id="ag-lwv",
        target_cities=["City of Flower Mound"], repo=_repo())


def test_viewer_cannot_manage_users(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    actor = resolve_principal({"email": "viewer@lwv.gov"}, _repo())
    with pytest.raises(AccessDenied):
        assert_can_manage_user(
            actor, target_email="x@lwv.gov", target_role="viewer",
            target_agency_id="ag-lwv", target_cities=[], repo=_repo())


def test_only_platform_admin_manages_agencies(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", ["boss@city.gov"])
    plat = resolve_principal({"email": "boss@city.gov"}, _repo())
    assert_can_manage_agency(plat)                 # no raise
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    agadmin = resolve_principal({"email": "agencyadmin@lwv.gov"}, _repo())
    with pytest.raises(AccessDenied):
        assert_can_manage_agency(agadmin)


def test_legacy_admin_role_maps_to_platform(monkeypatch):
    from core import config
    monkeypatch.setattr(config, "ADMIN_EMAILS", [])
    repo = FakeRepo(users=[{"email": "old@city.gov", "role": "admin", "city": "City of X"}])
    p = resolve_principal({"email": "old@city.gov"}, repo)
    assert p.role == ROLE_PLATFORM_ADMIN and p.all_cities
