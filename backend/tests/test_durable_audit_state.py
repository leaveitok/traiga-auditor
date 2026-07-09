"""
test_durable_audit_state.py — regression tests for durable, cross-instance
audit-run state (ROADMAP H1-2).

Covers three layers:
  1. Pure decision logic in core/run_state.py (the lease/claim math shared by
     every repository backend).
  2. MockGovernanceRepository's run-state methods (the same read-modify-write
     shape SheetsRepository and FirestoreRepository implement).
  3. The audit route: GET /api/audit/run reads shared state (not a per-process
     global), and the "already running" 409 guard is enforced via the durable
     claim.

Layers 1–2 need no FastAPI TestClient and run under the standalone shim runner.
Layer 3 uses the TestClient fixture (local pytest / CI).
"""
from datetime import datetime, timedelta, timezone

import pytest

from core import run_state as _rs
from core.governance_service import GovernanceRepository
from tests.mock_repository import MockGovernanceRepository


def _iso(dt: datetime) -> str:
    return dt.isoformat()


NOW_DT = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
NOW = _iso(NOW_DT)


# ── Layer 1: pure decision logic ─────────────────────────────────────────────

def test_parse_iso_is_forgiving():
    assert _rs.parse_iso(None) is None
    assert _rs.parse_iso("") is None
    assert _rs.parse_iso("garbage") is None
    assert _rs.parse_iso("2026-07-08T12:00:00Z") == NOW_DT
    # naive strings are coerced to UTC (never crash the lease math)
    assert _rs.parse_iso("2026-07-08T12:00:00").tzinfo is not None


def test_default_and_running_templates():
    d = _rs.default_audit_state()
    assert d["status"] == "idle" and d["progress"] is None and d["city_count"] == 0
    r = _rs.running_state(NOW, 11)
    assert r["status"] == "running"
    assert r["started_utc"] == NOW and r["heartbeat_utc"] == NOW
    assert r["progress"] == {"current_city": "", "completed": 0, "total": 11}


def test_slot_available_when_free():
    assert _rs.slot_available(None, NOW, 900) is True
    assert _rs.slot_available({}, NOW, 900) is True
    assert _rs.slot_available({"status": "completed"}, NOW, 900) is True
    assert _rs.slot_available({"status": "error"}, NOW, 900) is True
    assert _rs.slot_available({"status": "idle"}, NOW, 900) is True


def test_slot_locked_while_holder_fresh():
    fresh = {"status": "running",
             "heartbeat_utc": _iso(NOW_DT - timedelta(seconds=60)),
             "started_utc":   _iso(NOW_DT - timedelta(seconds=120))}
    assert _rs.slot_available(fresh, NOW, 900) is False


def test_slot_stealable_when_holder_stale():
    stale = {"status": "running",
             "heartbeat_utc": _iso(NOW_DT - timedelta(seconds=1000))}
    assert _rs.slot_available(stale, NOW, 900) is True


def test_stale_threshold_is_strict():
    at = {"status": "running", "heartbeat_utc": _iso(NOW_DT - timedelta(seconds=900))}
    just = {"status": "running", "heartbeat_utc": _iso(NOW_DT - timedelta(seconds=901))}
    assert _rs.slot_available(at, NOW, 900) is False      # exactly at limit: still held
    assert _rs.slot_available(just, NOW, 900) is True     # 1s past: stealable


def test_running_without_timestamps_never_wedges():
    # A running holder with no parseable heartbeat/started is treated as stale
    # so a crashed run can never block all future audits forever.
    assert _rs.slot_available({"status": "running"}, NOW, 900) is True


def test_running_falls_back_to_started_when_no_heartbeat():
    nohb_fresh = {"status": "running", "started_utc": _iso(NOW_DT - timedelta(seconds=30))}
    assert _rs.slot_available(nohb_fresh, NOW, 900) is False


# ── Layer 2: repository run-state methods (Mock) ─────────────────────────────

def test_mock_still_satisfies_protocol_with_new_methods():
    assert isinstance(MockGovernanceRepository(), GovernanceRepository)


def test_run_state_defaults_empty_and_round_trips():
    repo = MockGovernanceRepository()
    assert repo.get_run_state(_rs.AUDIT_KEY) == {}
    repo.save_run_state(_rs.AUDIT_KEY, {"status": "running", "progress": {"completed": 2}})
    got = repo.get_run_state(_rs.AUDIT_KEY)
    assert got["status"] == "running" and got["progress"]["completed"] == 2
    # returned dict is a copy — mutating it must not corrupt stored state
    got["status"] = "tampered"
    assert repo.get_run_state(_rs.AUDIT_KEY)["status"] == "running"


def test_claim_is_exclusive_then_releases():
    repo = MockGovernanceRepository()
    first = repo.claim_run_slot(_rs.AUDIT_KEY, now_utc=NOW, total=11, stale_after_seconds=900)
    assert first is not None and first["status"] == "running" and first["progress"]["total"] == 11
    # second concurrent claim is rejected (this is the cross-instance 409)
    assert repo.claim_run_slot(_rs.AUDIT_KEY, now_utc=NOW, total=11, stale_after_seconds=900) is None
    # holder finishes → slot frees → a new run may claim
    repo.save_run_state(_rs.AUDIT_KEY, {**_rs.default_audit_state(), "status": "completed"})
    assert repo.claim_run_slot(_rs.AUDIT_KEY, now_utc=NOW, total=3, stale_after_seconds=900) is not None


def test_claim_steals_a_stale_lease():
    repo = MockGovernanceRepository()
    assert repo.claim_run_slot(_rs.AUDIT_KEY, now_utc=NOW, total=5, stale_after_seconds=900) is not None
    # a crashed holder never heartbeats; a much later claim supersedes it
    later = _iso(NOW_DT + timedelta(seconds=1000))
    assert repo.claim_run_slot(_rs.AUDIT_KEY, now_utc=later, total=5, stale_after_seconds=900) is not None


def test_audit_and_scheduler_keys_are_independent():
    repo = MockGovernanceRepository()
    repo.save_run_state(_rs.SCHEDULER_KEY, {"run_count": 4})
    assert repo.claim_run_slot(_rs.AUDIT_KEY, now_utc=NOW, total=1, stale_after_seconds=900) is not None
    assert repo.get_run_state(_rs.SCHEDULER_KEY)["run_count"] == 4


# ── Layer 3: audit route reads/writes durable state (local TestClient) ───────

def _mk_client(repo):
    from fastapi.testclient import TestClient
    from main import app
    from core.dependencies import get_repository
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app), app


def test_get_run_reads_shared_state():
    repo = MockGovernanceRepository()
    repo.save_run_state(_rs.AUDIT_KEY, {
        **_rs.default_audit_state(),
        "status":     "running",
        "city_count": 3,
        "progress":   {"current_city": "Denton", "completed": 1, "total": 3},
    })
    client, app = _mk_client(repo)
    try:
        with client:
            r = client.get("/api/audit/run")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "running"
        assert data["progress"]["completed"] == 1
        assert data["city_count"] == 3
    finally:
        app.dependency_overrides.clear()


def test_trigger_returns_409_when_a_fresh_run_holds_the_slot():
    repo = MockGovernanceRepository()
    # Simulate another instance mid-scan with a fresh lease.
    repo.save_run_state(_rs.AUDIT_KEY, _rs.running_state(_rs.now_iso(), 2))
    client, app = _mk_client(repo)
    try:
        with client:
            r = client.post("/api/audit/run", params={"demo": "true"})
        assert r.status_code == 409
        assert "already running" in r.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()
