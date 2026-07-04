"""
conftest.py — Shared pytest fixtures for the AI Transparency Auditor test suite.

All fixtures use app.dependency_overrides to inject MockGovernanceRepository
without touching Google Sheets, Firebase, or any network resource.

REQUIRE_AUTH defaults to false in config.py, so requests without a Bearer token
automatically receive the synthetic admin user (leaveitok@gmail.com).
To test non-admin paths, override get_current_user separately.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure the backend root is on the path regardless of where pytest runs from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test env vars BEFORE importing main (config.py reads env at import time)
os.environ.setdefault("REQUIRE_AUTH", "false")
os.environ.setdefault("ADMIN_EMAILS", "admin@test.gov")
os.environ.setdefault("SPREADSHEET_ID", "test-sheet-id")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

from main import app
from core.dependencies import get_repository
from core.auth import get_current_user
from tests.mock_repository import MockGovernanceRepository

# ── Reusable test data ────────────────────────────────────────────────────────

SAMPLE_TARGET = {
    "id": "1", "city": "Test City", "jurisdiction": "TX",
    "domain": "testcity.gov", "url": "https://testcity.gov",
    "tags": ["chatbot"], "active": True, "added_utc": "2026-01-01T00:00:00Z",
}

SAMPLE_SCORECARD_ROW = {
    "city": "Test City", "jurisdiction": "TX", "domain": "testcity.gov",
    "traiga_status": "in_cure", "compliance_score": 60,
    "band": "amber", "open_violations_count": 2,
    "min_days_remaining": 30, "last_scanned_utc": "2026-01-15T00:00:00Z",
    "ai_assets_json": '[{"vendor_id":"citibot","display_name":"Citibot"}]',
}

SAMPLE_VIOLATION = {
    "violation_id": "v-testcity-001", "city": "Test City",
    "rule_id": "ai_disclosure", "status": "open",
    "citation": "§552.051", "severity": "high",
    "days_remaining": 30, "evidence_json": "{}",
    "cure_period_status": "True", "needs_human_review": "True",
}


# ── Repository fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def empty_repo() -> MockGovernanceRepository:
    """Empty repository — no cities, no violations."""
    return MockGovernanceRepository()


@pytest.fixture
def populated_repo() -> MockGovernanceRepository:
    """Repository pre-loaded with one city, one scorecard row, one violation."""
    return MockGovernanceRepository(
        targets=[SAMPLE_TARGET],
        scorecard=[SAMPLE_SCORECARD_ROW],
        violations=[SAMPLE_VIOLATION],
    )


# ── Client fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def client(empty_repo):
    """
    TestClient with empty repository and synthetic admin user
    (REQUIRE_AUTH=false → no token needed → admin@test.gov auto-injected).
    """
    app.dependency_overrides[get_repository] = lambda: empty_repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_data(populated_repo):
    """TestClient with one pre-loaded city."""
    app.dependency_overrides[get_repository] = lambda: populated_repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def city_user_client(populated_repo):
    """
    TestClient where the authenticated user is a city-scoped user (not admin).
    Useful for testing 403 enforcement on admin-only endpoints.
    """
    app.dependency_overrides[get_repository] = lambda: populated_repo
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": "city-user-1",
        "email": "staff@testcity.gov",
        "role": "city",
        "city": "Test City",
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
