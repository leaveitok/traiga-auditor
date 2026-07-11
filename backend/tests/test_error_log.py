"""test_error_log.py — durable error log + fail-safe recorder.

The recorder's core contract: recording an error must NEVER raise, even when
the underlying repository write fails. The original exception the caller is
handling always takes precedence.
"""
from core.error_log import record_error, LEVEL_WARNING
from tests.mock_repository import MockGovernanceRepository


def test_append_and_get_most_recent_first():
    repo = MockGovernanceRepository()
    repo.append_error_log(source="scheduler", message="first")
    repo.append_error_log(source="audit_pipeline", message="second")
    rows = repo.get_error_log()
    assert [r["message"] for r in rows] == ["second", "first"]   # newest first
    assert rows[0]["source"] == "audit_pipeline"
    assert rows[0]["level"] == "error"                            # default level


def test_record_error_writes_through_repo():
    repo = MockGovernanceRepository()
    ok = record_error(repo, source="audit_pipeline", message="KeyError: 'x'",
                      city="Lewisville", details={"ref": "ab12cd34"})
    assert ok is True
    row = repo.get_error_log()[0]
    assert row["source"] == "audit_pipeline"
    assert row["city"] == "Lewisville"
    assert row["details"]["ref"] == "ab12cd34"
    assert row["level"] == "error"


def test_record_error_never_raises_on_broken_repo():
    class BrokenRepo:
        def append_error_log(self, *a, **k):
            raise RuntimeError("firestore unavailable")
    # Must swallow the write failure and report False — not propagate.
    result = record_error(BrokenRepo(), source="scheduler", message="boom")
    assert result is False


def test_record_error_truncates_long_message():
    repo = MockGovernanceRepository()
    record_error(repo, source="x", message="A" * 5000, level=LEVEL_WARNING)
    row = repo.get_error_log()[0]
    assert len(row["message"]) < 5000 and row["message"].endswith("…[truncated]")
    assert row["level"] == "warning"
