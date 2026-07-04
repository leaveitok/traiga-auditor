"""
test_auth_routes.py — Smoke tests for /api/auth endpoints.

Tests verify:
  - Admin users get role=admin from /me
  - City users get role=city from /me
  - list_users enforces admin-only
  - upsert_user enforces admin-only

NOTE: admin_client and city_client fixtures must NEVER be used in the same test.
Both modify app.dependency_overrides on the shared app instance — combining them
in one test causes fixture ordering to stomp the other's get_current_user override.
Each access-control check is its own test for isolation.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_repository
from core.auth import get_current_user
from tests.mock_repository import MockGovernanceRepository


@pytest.fixture
def admin_client(empty_repo):
    """
    Client authenticated as an explicit admin user.
    Overrides get_current_user so the admin identity is stable regardless
    of ADMIN_EMAILS env var or fixture ordering.
    """
    app.dependency_overrides[get_repository] = lambda: empty_repo
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "admin-1", "email": "admin@test.gov", "role": "admin", "city": None
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def city_client(populated_repo):
    """Client authenticated as a city-scoped non-admin user."""
    app.dependency_overrides[get_repository] = lambda: populated_repo
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "city-1", "email": "staff@testcity.gov", "role": "city", "city": "Test City"
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── /api/auth/me ─────────────────────────────────────────────────────────────

def test_get_me_admin(admin_client):
    """Admin email returns role=admin with no city assignment."""
    r = admin_client.get("/api/auth/me")
    assert r.status_code == 200
    profile = r.json()
    assert profile["role"] == "admin"
    assert profile["city"] is None


def test_get_me_city_user(city_client):
    """Provisioned city user returns role=city."""
    r = city_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "city"


# ── /api/auth/users GET ───────────────────────────────────────────────────────

def test_list_users_admin_success(admin_client):
    """Admin can list users."""
    r = admin_client.get("/api/auth/users")
    assert r.status_code == 200


def test_list_users_city_forbidden(city_client):
    """City-scoped user cannot list users."""
    r = city_client.get("/api/auth/users")
    assert r.status_code == 403


# ── /api/auth/users POST ──────────────────────────────────────────────────────

def test_upsert_user_admin_success(admin_client):
    """Admin can create a user."""
    payload = {"email": "new@city.gov", "role": "city", "city": "New City"}
    r = admin_client.post("/api/auth/users", json=payload)
    assert r.status_code == 200


def test_upsert_user_city_forbidden(city_client):
    """City-scoped user cannot create users."""
    payload = {"email": "new@city.gov", "role": "city", "city": "New City"}
    r = city_client.post("/api/auth/users", json=payload)
    assert r.status_code == 403


def test_upsert_user_persists_to_repo(admin_client, empty_repo):
    """Upserted user must be written to the repository."""
    payload = {"email": "officer@lewisville.gov", "role": "city", "city": "City of Lewisville"}
    r = admin_client.post("/api/auth/users", json=payload)
    assert r.status_code == 200
    user = empty_repo.get_user("officer@lewisville.gov")
    assert user is not None
    assert user["city"] == "City of Lewisville"
