"""
test_targets.py — Smoke tests for /api/targets.
"""


def test_list_targets_empty(client):
    r = client.get("/api/targets")
    assert r.status_code == 200
    assert r.json() == []


def test_list_targets_returns_active_only(client):
    """Only active targets are returned — inactive ones are hidden."""
    from tests.mock_repository import MockGovernanceRepository
    from main import app
    from core.dependencies import get_repository

    repo = MockGovernanceRepository(targets=[
        {"id": "1", "city": "Active City",   "active": True,  "jurisdiction": "TX", "domain": "a.gov", "url": "https://a.gov", "tags": []},
        {"id": "2", "city": "Inactive City", "active": False, "jurisdiction": "TX", "domain": "b.gov", "url": "https://b.gov", "tags": []},
    ])
    app.dependency_overrides[get_repository] = lambda: repo
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.get("/api/targets")
    app.dependency_overrides.clear()

    assert r.status_code == 200
    cities = [t["city"] for t in r.json()]
    assert "Active City" in cities
    assert "Inactive City" not in cities


def test_create_target(client, empty_repo):
    """POST /api/targets creates and returns the new target."""
    payload = {
        "city":         "New City",
        "jurisdiction": "TX",
        "domain":       "newcity.gov",
        "url":          "https://newcity.gov",
        "tags":         ["chatbot"],
    }
    r = client.post("/api/targets", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["city"] == "New City"
    assert created["active"] is True
    # Verify it's in the repo
    assert len(empty_repo.get_targets()) == 1


def test_delete_target_not_found(client):
    r = client.delete("/api/targets/nonexistent-id")
    assert r.status_code == 404


def test_deactivate_target(client, empty_repo):
    """DELETE soft-deactivates a target."""
    # Seed one target
    t = empty_repo.add_target("City X", "TX", "cityx.gov", "https://cityx.gov", [])
    r = client.delete(f"/api/targets/{t['id']}")
    assert r.status_code == 204
    # Should no longer appear in active list
    assert empty_repo.get_targets() == []
