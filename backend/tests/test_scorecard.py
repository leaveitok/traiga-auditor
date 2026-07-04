"""
test_scorecard.py — Smoke tests for GET /api/scorecard and /api/scorecard/summary.

These tests verify the route layer:
  - Returns correct HTTP status codes
  - Passes repository data through to the response
  - Enforces admin-only on DELETE
"""


def test_get_scorecard_empty(client):
    """Empty repository returns an empty list, not 500."""
    r = client.get("/api/scorecard")
    assert r.status_code == 200
    assert r.json() == []


def test_get_scorecard_returns_rows(client_with_data):
    """Scorecard rows from the repository are returned in the response."""
    r = client_with_data.get("/api/scorecard")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["city"] == "Test City"
    assert rows[0]["traiga_status"] == "in_cure"


def test_get_scorecard_parses_ai_assets_json(client_with_data):
    """ai_assets_json is parsed into a list, not returned as a raw string."""
    r = client_with_data.get("/api/scorecard")
    assert r.status_code == 200
    row = r.json()[0]
    assert "ai_assets" in row
    assert isinstance(row["ai_assets"], list)
    assert "ai_assets_json" not in row


def test_get_scorecard_summary_empty(client):
    """Summary over empty repo returns zeros, not 500."""
    r = client.get("/api/scorecard/summary")
    assert r.status_code == 200
    summary = r.json()
    assert summary["total_cities"] == 0
    assert summary["average_compliance_score"] is None


def test_get_scorecard_summary_with_data(client_with_data):
    """Summary reflects the one city in the populated repo."""
    r = client_with_data.get("/api/scorecard/summary")
    assert r.status_code == 200
    summary = r.json()
    assert summary["total_cities"] == 1
    assert summary["in_cure"] == 1
    assert summary["compliant"] == 0


def test_delete_scorecard_row_admin_success(client_with_data):
    """Admin can delete a scorecard row by city name."""
    r = client_with_data.delete("/api/scorecard/Test City")
    assert r.status_code == 200
    assert r.json()["deleted"] == "Test City"
    # Confirm the row is gone
    r2 = client_with_data.get("/api/scorecard")
    assert r2.json() == []


def test_delete_scorecard_row_not_found(client):
    """Deleting a city that doesn't exist returns 404."""
    r = client.delete("/api/scorecard/Ghost City")
    assert r.status_code == 404


def test_delete_scorecard_row_forbidden_for_city_user(city_user_client):
    """Non-admin users get 403 on DELETE."""
    r = city_user_client.delete("/api/scorecard/Test City")
    assert r.status_code == 403
