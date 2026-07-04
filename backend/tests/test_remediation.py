"""
test_remediation.py -- Tests for GET /api/remediation/policy endpoint.
"""
import pytest


# ── Fixtures shared by all remediation tests ─────────────────────────────────

def _make_repo_with_city(city="City of Lewisville"):
    """Return a MockGovernanceRepository pre-loaded with one assessed city."""
    import json
    from tests.mock_repository import MockGovernanceRepository

    assets = [{"vendor_id": "citibot", "display_name": "Citibot", "asset_type": ["chatbot"]}]
    violations = [
        {
            "violation_id": "v1",
            "city": city,
            "rule_id": "TRAIGA-01",
            "severity": "high",
            "status": "open",
            "cure_period_status": "True",
            "needs_human_review": "False",
            "cure_deadline_utc": "2026-03-01T00:00:00Z",
            "days_remaining": "30",
        }
    ]
    scorecard = [
        {
            "city": city,
            "jurisdiction": "TX",
            "domain": "cityoflewisville.com",
            "traiga_status": "in_cure",
            "compliance_score": 55,
            "open_violations_count": 1,
            "ai_assets": json.dumps(assets),
            "last_scanned": "2026-01-15T12:00:00Z",
        }
    ]
    targets = [
        {
            "id": "t1",
            "city": city,
            "jurisdiction": "TX",
            "domain": "cityoflewisville.com",
            "url": "https://cityoflewisville.com",
            "tags": [],
            "active": True,
            "cloudflare_protected": False,
        }
    ]
    return MockGovernanceRepository(
        targets=targets,
        scorecard=scorecard,
        violations=violations,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_policy_returns_docx(client):
    """GET /api/remediation/policy returns a .docx file for a known city."""
    from main import app
    from core.dependencies import get_repository

    repo = _make_repo_with_city()
    app.dependency_overrides[get_repository] = lambda: repo
    try:
        r = client.get("/api/remediation/policy", params={"city": "City of Lewisville"})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert "wordprocessingml" in r.headers.get("content-type", "")


def test_policy_filename_contains_city(client):
    """Content-Disposition header carries the city-derived filename."""
    from main import app
    from core.dependencies import get_repository

    repo = _make_repo_with_city()
    app.dependency_overrides[get_repository] = lambda: repo
    try:
        r = client.get("/api/remediation/policy", params={"city": "City of Lewisville"})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "AI_Use_Policy.docx" in cd


def test_policy_missing_city_param(client):
    """GET /api/remediation/policy without city param returns 422."""
    r = client.get("/api/remediation/policy")
    assert r.status_code == 422


def test_policy_unknown_city_still_generates(client):
    """
    An unknown city (not in scorecard/targets) still generates a valid document
    with zero assets and zero violations — graceful degradation, not a 500.
    """
    from main import app
    from core.dependencies import get_repository
    from tests.mock_repository import MockGovernanceRepository

    empty_repo = MockGovernanceRepository()
    app.dependency_overrides[get_repository] = lambda: empty_repo
    try:
        r = client.get(
            "/api/remediation/policy",
            params={"city": "City of Nowhere"},
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    assert "wordprocessingml" in r.headers.get("content-type", "")


def test_policy_generator_produces_valid_docx(tmp_path):
    """
    Unit-test engine.remediation.policy_generator directly — no HTTP layer.
    Asserts the output file is a valid .docx (non-empty, correct extension).
    """
    from engine.remediation.policy_generator import generate_ai_use_policy

    out = str(tmp_path / "test_policy.docx")
    result_path = generate_ai_use_policy(
        city="Test City",
        jurisdiction="TX",
        domain="testcity.gov",
        detected_assets=[
            {"vendor_id": "citibot", "display_name": "Citibot"}
        ],
        violations=[],
        output_path=out,
        scan_date="2026-01-01T00:00:00Z",
    )
    assert result_path == out
    import os
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1_000


def test_policy_generator_vendor_profiles():
    """VENDOR_PROFILES covers the four expected vendors."""
    from engine.remediation.policy_generator import VENDOR_PROFILES

    for vid in ("citibot", "civicplus", "govpilot", "municode"):
        assert vid in VENDOR_PROFILES, f"Missing vendor profile: {vid}"
        assert VENDOR_PROFILES[vid]["display_name"]
        assert VENDOR_PROFILES[vid]["primary_use"]
