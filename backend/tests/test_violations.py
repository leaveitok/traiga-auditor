"""
test_violations.py — Smoke tests for GET /api/violations.
"""


def test_list_violations_empty(client):
    r = client.get("/api/violations")
    assert r.status_code == 200
    assert r.json() == []


def test_list_violations_returns_rows(client_with_data):
    r = client_with_data.get("/api/violations")
    assert r.status_code == 200
    violations = r.json()
    assert len(violations) == 1
    assert violations[0]["city"] == "Test City"
    assert violations[0]["rule_id"] == "ai_disclosure"


def test_list_violations_filter_by_city(client_with_data):
    """city query param filters results."""
    r = client_with_data.get("/api/violations?city=Test+City")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r2 = client_with_data.get("/api/violations?city=Other+City")
    assert r2.status_code == 200
    assert r2.json() == []


def test_list_violations_filter_by_status(client_with_data):
    """status query param filters results."""
    r = client_with_data.get("/api/violations?status=open")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r2 = client_with_data.get("/api/violations?status=cured")
    assert r2.status_code == 200
    assert r2.json() == []


def test_get_violation_by_id(client_with_data):
    """Individual violation lookup by ID."""
    r = client_with_data.get("/api/violations/v-testcity-001")
    assert r.status_code == 200
    assert r.json()["violation_id"] == "v-testcity-001"


def test_get_violation_not_found(client):
    r = client.get("/api/violations/nonexistent-id")
    assert r.status_code == 404


def test_violations_parses_evidence_json(client_with_data):
    """evidence_json column is parsed into a dict, not a raw string."""
    r = client_with_data.get("/api/violations")
    v = r.json()[0]
    assert "evidence" in v
    assert isinstance(v["evidence"], dict)
    assert "evidence_json" not in v
