"""
test_audit_log_coverage.py — destructive admin actions MUST leave an audit trail.

The product sells auditability; a delete that leaves no record is the exact gap an
auditor flags. These pin the two destructive admin endpoints that previously logged
nothing: scorecard-row delete and violation purge.
"""
from api.routes.scorecard import delete_scorecard_row
from api.routes.violations import purge_dirty_violations
from tests.mock_repository import MockGovernanceRepository

ADMIN = {"email": "leaveitok@gmail.com"}   # platform-admin bootstrap (ADMIN_EMAILS)


def test_scorecard_row_delete_is_audited():
    repo = MockGovernanceRepository(scorecard=[{"city": "Ghost City"}])
    delete_scorecard_row("Ghost City", ADMIN, repo)
    log = repo.get_audit_log()
    assert any(e["event"] == "scorecard_row_deleted" for e in log), [e["event"] for e in log]
    entry = next(e for e in log if e["event"] == "scorecard_row_deleted")
    assert entry["details"]["actor"] == "leaveitok@gmail.com"
    assert entry["details"]["city"] == "Ghost City"


def test_violation_purge_is_audited():
    repo = MockGovernanceRepository(
        violations=[{"violation_id": "v1", "domain": "[BLOCKED]token", "status": "open"},
                    {"violation_id": "v2", "domain": "lewisville.gov", "status": "open"}])
    purge_dirty_violations("[BLOCKED", ADMIN, repo)
    log = repo.get_audit_log()
    assert any(e["event"] == "violations_purged" for e in log), [e["event"] for e in log]
    entry = next(e for e in log if e["event"] == "violations_purged")
    assert entry["details"]["removed"] == 1
    assert entry["details"]["actor"] == "leaveitok@gmail.com"
