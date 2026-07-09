"""
test_sentinel.py — AI-GRC Sentinel module tests.

Covers the two trust domains:
  ingest: device-token auth (fail-secure when unconfigured), packet validation,
          rejection of content-bearing packets (metadata-only contract),
  reads:  admin allowed, city user 403, silent-device computation.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from main import app
from core.auth import get_current_user
from core.dependencies import get_sentinel_repository
from core.repositories.sentinel_repository import MemorySentinelRepository

TOKEN = "test-device-token-123"


def _violation_packet(**over):
    p = {
        "packet_type": "violation",
        "schema_version": "1.0.0",
        "event_id": "ev-test-0001",
        "timestamp_utc": "2026-07-04T16:22:09Z",
        "device_id": "LWV-LT-04471",
        "user_id": "jdoe@cityoflewisville.com",
        "extension_version": "0.1.0",
        "ruleset_version": "2026.07.04",
        "browser": {"name": "edge", "version": "126.0"},
        "app": {"site_id": "chatgpt", "origin": "https://chatgpt.com"},
        "trigger": "submit_click",
        "payload_class": "text",
        "detections": [{"policy_id": "TX-PII-SSN", "pattern_id": "ssn_formatted",
                        "match_count": 2, "confidence": 0.95}],
        "action_taken": "blocked",
    }
    p.update(over)
    return p


def _heartbeat_packet(**over):
    p = {
        "packet_type": "heartbeat",
        "schema_version": "1.0.0",
        "event_id": "hb-test-0001",
        "timestamp_utc": "2026-07-04T16:00:00Z",
        "device_id": "LWV-LT-04471",
        "user_id": "jdoe@cityoflewisville.com",
        "extension_version": "0.1.0",
        "ruleset_version": "2026.07.04",
        "policies_loaded": 6,
        "last_scan_utc": None,
        "status": "ok",
    }
    p.update(over)
    return p


@pytest.fixture
def sentinel_repo():
    return MemorySentinelRepository()


@pytest.fixture
def sclient(sentinel_repo, monkeypatch):
    """Client with ingest token configured and admin reads (REQUIRE_AUTH=false)."""
    monkeypatch.setenv("SENTINEL_INGEST_TOKENS", TOKEN)
    app.dependency_overrides[get_sentinel_repository] = lambda: sentinel_repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def city_sclient(sentinel_repo, monkeypatch):
    """Client authenticated as a city-scoped (non-security) user."""
    monkeypatch.setenv("SENTINEL_INGEST_TOKENS", TOKEN)
    app.dependency_overrides[get_sentinel_repository] = lambda: sentinel_repo
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "city-user-1", "email": "staff@testcity.gov", "role": "city", "city": "Test City",
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Ingest auth ────────────────────────────────────────────────────────────────
def test_ingest_fail_secure_when_unconfigured(sentinel_repo, monkeypatch):
    monkeypatch.delenv("SENTINEL_INGEST_TOKENS", raising=False)
    app.dependency_overrides[get_sentinel_repository] = lambda: sentinel_repo
    with TestClient(app) as c:
        r = c.post("/api/sentinel/ingest", json=_violation_packet(),
                   headers={"X-Sentinel-Token": TOKEN})
    app.dependency_overrides.clear()
    assert r.status_code == 503
    assert sentinel_repo.events == []


def test_ingest_rejects_bad_or_missing_token(sclient, sentinel_repo):
    assert sclient.post("/api/sentinel/ingest", json=_violation_packet()).status_code == 401
    assert sclient.post("/api/sentinel/ingest", json=_violation_packet(),
                        headers={"X-Sentinel-Token": "wrong"}).status_code == 401
    assert sentinel_repo.events == []


# ── Packet validation (metadata-only contract) ────────────────────────────────
def test_ingest_accepts_valid_violation(sclient, sentinel_repo):
    r = sclient.post("/api/sentinel/ingest", json=_violation_packet(),
                     headers={"X-Sentinel-Token": TOKEN})
    assert r.status_code == 202
    assert len(sentinel_repo.events) == 1
    assert sentinel_repo.events[0]["action_taken"] == "blocked"


def test_ingest_rejects_content_bearing_packet(sclient, sentinel_repo):
    """extra='forbid' — a packet with prompt text must be rejected, not stripped."""
    bad = _violation_packet(prompt_text="my SSN is 453-98-1122")
    r = sclient.post("/api/sentinel/ingest", json=bad, headers={"X-Sentinel-Token": TOKEN})
    assert r.status_code == 422
    assert sentinel_repo.events == []


def test_ingest_rejects_url_with_path(sclient, sentinel_repo):
    bad = _violation_packet(app={"site_id": "chatgpt",
                                 "origin": "https://chatgpt.com/c/abc123-convo"})
    r = sclient.post("/api/sentinel/ingest", json=bad, headers={"X-Sentinel-Token": TOKEN})
    assert r.status_code == 422
    assert sentinel_repo.events == []


def test_ingest_accepts_heartbeat(sclient, sentinel_repo):
    r = sclient.post("/api/sentinel/ingest", json=_heartbeat_packet(),
                     headers={"X-Sentinel-Token": TOKEN})
    assert r.status_code == 202
    assert len(sentinel_repo.heartbeats) == 1


# ── Read RBAC (agency-scoped, not a hard wall) ───────────────────────────────
def test_agency_user_sees_only_their_own_cities(sentinel_repo, monkeypatch):
    """Sentinel reads are agency-scoped: the platform admin sees every city's
    DLP events; an agency viewer granted 'Test City' sees ONLY that city's
    events, never another city's. (Supersedes the old hard admin/security-only
    wall — see the agency multi-tenant model in core/access.py.)

    Single TestClient context throughout; the admin read uses the synthetic
    admin (no get_current_user override) exactly like test_admin_reads_*.
    try/finally guarantees overrides never leak into the next test.
    """
    monkeypatch.setenv("SENTINEL_INGEST_TOKENS", TOKEN)
    from tests.mock_repository import MockGovernanceRepository
    from core.dependencies import get_repository

    gov = MockGovernanceRepository(users=[{
        "email": "staff@testcity.gov", "role": "viewer",
        "cities": ["Test City"], "city": "Test City",
    }])
    app.dependency_overrides[get_sentinel_repository] = lambda: sentinel_repo
    app.dependency_overrides[get_repository] = lambda: gov
    try:
        with TestClient(app) as c:
            # Ingest one event tagged to each city (device-token auth path).
            assert c.post("/api/sentinel/ingest",
                          json=_violation_packet(event_id="ev-testcity-01", city="Test City"),
                          headers={"X-Sentinel-Token": TOKEN}).status_code == 202
            assert c.post("/api/sentinel/ingest",
                          json=_violation_packet(event_id="ev-othercity-01", city="Other City"),
                          headers={"X-Sentinel-Token": TOKEN}).status_code == 202

            # Platform admin (synthetic, no override — all_cities) sees BOTH.
            admin_rows = c.get("/api/sentinel/events")
            assert admin_rows.status_code == 200
            assert {r.get("city") for r in admin_rows.json()} == {"Test City", "Other City"}

            # Agency viewer scoped to "Test City" sees ONLY that city's events.
            app.dependency_overrides[get_current_user] = lambda: {
                "uid": "city-1", "email": "staff@testcity.gov",
                "role": "viewer", "city": "Test City",
            }
            scoped = c.get("/api/sentinel/events")
            assert scoped.status_code == 200
            assert {r.get("city") for r in scoped.json()} == {"Test City"}
    finally:
        app.dependency_overrides.clear()


def test_admin_reads_events_and_summary(sclient):
    sclient.post("/api/sentinel/ingest", json=_violation_packet(),
                 headers={"X-Sentinel-Token": TOKEN})
    events = sclient.get("/api/sentinel/events").json()
    assert len(events) == 1
    assert events[0]["detections"][0]["policy_id"] == "TX-PII-SSN"
    assert "detections_json" not in events[0]
    s = sclient.get("/api/sentinel/summary").json()
    assert s["total_events"] == 1 and s["blocked"] == 1
    assert s["by_policy"]["TX-PII-SSN"] == 1


def test_device_silent_flag(sclient):
    """Old heartbeat -> silent (tamper canary); fresh heartbeat -> reporting."""
    from datetime import datetime, timedelta, timezone
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    r1 = sclient.post("/api/sentinel/ingest",
                      json=_heartbeat_packet(device_id="DEV-FRESH", timestamp_utc=fresh),
                      headers={"X-Sentinel-Token": TOKEN})
    r2 = sclient.post("/api/sentinel/ingest",
                      json=_heartbeat_packet(event_id="hb-stale-0002", device_id="DEV-STALE", timestamp_utc=stale),
                      headers={"X-Sentinel-Token": TOKEN})
    assert r1.status_code == 202, r1.text
    assert r2.status_code == 202, r2.text
    devices = {d["device_id"]: d for d in sclient.get("/api/sentinel/devices").json()}
    assert devices["DEV-FRESH"]["silent"] is False
    assert devices["DEV-STALE"]["silent"] is True


def test_repository_defense_in_depth():
    """Storage layer itself rejects content-bearing fields regardless of route."""
    repo = MemorySentinelRepository()
    with pytest.raises(ValueError):
        repo.store_event({"event_id": "x", "prompt_text": "leak"})
