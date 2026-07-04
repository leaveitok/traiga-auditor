"""
test_governance_protocol.py — Verify MockGovernanceRepository satisfies the Protocol.

This is the first test that must pass. If MockRepository doesn't implement the
full Protocol, every other test built on it is unreliable.
"""
from tests.mock_repository import MockGovernanceRepository
from core.governance_service import GovernanceRepository


def test_mock_satisfies_protocol():
    """MockGovernanceRepository must pass the runtime Protocol check."""
    mock = MockGovernanceRepository()
    assert isinstance(mock, GovernanceRepository), (
        "MockGovernanceRepository does not satisfy the GovernanceRepository Protocol. "
        "Add any missing methods listed in governance_service.py."
    )


def test_mock_is_independent_between_instances():
    """Each MockRepository instance must have isolated state."""
    a = MockGovernanceRepository(scorecard=[{"city": "City A"}])
    b = MockGovernanceRepository(scorecard=[{"city": "City B"}])
    assert a.get_scorecard()[0]["city"] == "City A"
    assert b.get_scorecard()[0]["city"] == "City B"
    # Mutating a must not affect b
    a.write_scorecard_rows([{"city": "City A Modified"}])
    assert b.get_scorecard()[0]["city"] == "City B"
