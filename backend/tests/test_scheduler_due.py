"""test_scheduler_due.py — the daily-scan due-gate (enabled + hour + not-run-today)."""
from datetime import datetime, timezone

from core.scheduler import scheduled_scan_due, stamp_scheduled_today
from core import settings
from tests.mock_repository import MockGovernanceRepository


def _at(hour):
    return datetime(2026, 7, 11, hour, 0, 0, tzinfo=timezone.utc)


def test_due_at_scheduled_hour_first_time():
    r = MockGovernanceRepository()
    settings.save(r, {"SCAN_SCHEDULE_ENABLED": True, "SCAN_SCHEDULE_HOUR": 7})
    due, info = scheduled_scan_due(r, now=_at(7))
    assert due is True, info


def test_not_due_wrong_hour():
    r = MockGovernanceRepository()
    settings.save(r, {"SCAN_SCHEDULE_ENABLED": True, "SCAN_SCHEDULE_HOUR": 7})
    due, info = scheduled_scan_due(r, now=_at(8))
    assert due is False and info["reason"] == "not_scheduled_hour"


def test_not_due_already_ran_today():
    r = MockGovernanceRepository()
    settings.save(r, {"SCAN_SCHEDULE_ENABLED": True, "SCAN_SCHEDULE_HOUR": 7})
    stamp_scheduled_today(r, now=_at(7))
    due, info = scheduled_scan_due(r, now=_at(7))
    assert due is False and info["reason"] == "already_ran_today"


def test_not_due_when_disabled():
    r = MockGovernanceRepository()
    settings.save(r, {"SCAN_SCHEDULE_ENABLED": False, "SCAN_SCHEDULE_HOUR": 7})
    due, info = scheduled_scan_due(r, now=_at(7))
    assert due is False and info["reason"] == "disabled"


def test_hour_is_clamped_to_valid_range():
    # 25 -> clamped to 23 by the settings int coercion (min 0, max 23)
    r = MockGovernanceRepository()
    eff = settings.save(r, {"SCAN_SCHEDULE_HOUR": 25})
    assert eff["SCAN_SCHEDULE_HOUR"] == 23
