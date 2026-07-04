"""
test_audit_route.py -- Smoke tests for /api/audit endpoints.
"""
import pytest


def test_schedule_status_endpoint(client):
    """GET /api/audit/schedule returns scheduler metadata."""
    r = client.get("/api/audit/schedule")
    assert r.status_code == 200
    data = r.json()
    assert "scan_cadence_hours" in data
    assert "auto_scan_cities" in data
    assert "manual_scan_cities" in data
    assert "scheduler_running" in data


def test_schedule_status_cloudflare_counts(client):
    """manual_scan_cities count reflects cloudflare_protected targets."""
    from tests.mock_repository import MockGovernanceRepository
    from main import app
    from core.dependencies import get_repository

    repo = MockGovernanceRepository(targets=[
        {
            "id": "1", "city": "Auto City", "active": True,
            "cloudflare_protected": False,
            "jurisdiction": "TX", "domain": "a.gov",
            "url": "https://a.gov", "tags": [],
        },
        {
            "id": "2", "city": "Blocked City", "active": True,
            "cloudflare_protected": True,
            "jurisdiction": "TX", "domain": "b.gov",
            "url": "https://b.gov", "tags": [],
        },
    ])
    app.dependency_overrides[get_repository] = lambda: repo
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.get("/api/audit/schedule")
    app.dependency_overrides.clear()

    assert r.status_code == 200
    data = r.json()
    assert data["auto_scan_cities"]   == 1
    assert data["manual_scan_cities"] == 1
    assert "Blocked City" in data["manual_city_names"]


def test_audit_status_idle_on_startup(client):
    """Audit status should be idle when no audit has run."""
    r = client.get("/api/audit/run")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("idle", "completed", "error")
    assert "city_count" in data
    assert "open_violations" in data


def test_chrome_capture_requires_city_when_persist_true(client):
    """chrome-capture with persist=True but no city returns 400."""
    r = client.post("/api/audit/chrome-capture", json={
        "url":     "https://example.gov",
        "html":    "<html></html>",
        "persist": True,
    })
    assert r.status_code == 400
    assert "city" in r.json()["detail"].lower()


def test_chrome_capture_no_persist_returns_fingerprint(client):
    """chrome-capture with persist=False returns fingerprint results."""
    r = client.post("/api/audit/chrome-capture", json={
        "url":          "https://example.gov",
        "html":         "<html><script src='https://cdn.citibot.io/widget.js'></script></html>",
        "script_hosts": ["cdn.citibot.io"],
        "persist":      False,
    })
    assert r.status_code == 200
    data = r.json()
    assert "detected_assets" in data
    assert "match_threshold" in data
    assert data["persisted"] is False


def test_chrome_capture_detects_citibot(client):
    """Citibot fingerprint should be detected from known script host."""
    r = client.post("/api/audit/chrome-capture", json={
        "url":            "https://cityoflewisville.gov",
        "html":           "<html><body><iframe src='https://webchat-ui.citibot.net/'></iframe></body></html>",
        "script_hosts":   ["cdn.citibot.io"],
        "iframe_origins": ["webchat-ui.citibot.net"],
        "persist":        False,
    })
    assert r.status_code == 200
    assets = r.json()["detected_assets"]
    vendor_ids = [a["vendor_id"] for a in assets]
    assert "citibot" in vendor_ids
