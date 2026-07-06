"""
test_inventory.py — AI Use-Case Inventory: merge contract, discovery feed,
RBAC scoping, lifecycle transitions.

Runs under pytest, or standalone: python3 tests/test_inventory.py
(the sandbox has no PyPI access; standalone mode needs no FastAPI).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.access import resolve_principal, filter_rows
from engine.pipeline import _asset_key, _feed_inventory
from tests.mock_repository import MockGovernanceRepository


def _repo(**kw) -> MockGovernanceRepository:
    return MockGovernanceRepository(**kw)


# ── Merge contract: scans never clobber human fields ─────────────────────────

def test_upsert_merge_preserves_human_fields():
    repo = _repo()
    repo.upsert_ai_asset({
        "asset_key": "city-of-denton::repd", "city": "City of Denton",
        "vendor_id": "repd", "lifecycle_status": "attested",
        "owner_email": "owner@denton.gov", "purpose": "Resident Q&A",
    })
    # A later scan writes machine fields only.
    repo.upsert_ai_asset({
        "asset_key": "city-of-denton::repd",
        "last_observed_utc": "2026-07-06T00:00:00Z",
        "match_confidence": "1.0", "presence": "active",
    })
    row = repo.get_ai_assets(city="City of Denton")[0]
    assert row["owner_email"] == "owner@denton.gov", "scan clobbered owner"
    assert row["lifecycle_status"] == "attested", "scan clobbered lifecycle"
    assert row["purpose"] == "Resident Q&A", "scan clobbered purpose"
    assert row["last_observed_utc"] == "2026-07-06T00:00:00Z"


def test_upsert_requires_asset_key():
    repo = _repo()
    try:
        repo.upsert_ai_asset({"city": "X"})
        assert False, "expected ValueError"
    except ValueError:
        pass


# ── Discovery feed (pipeline hook) ────────────────────────────────────────────

_DETECTED = [{
    "vendor_id": "repd", "display_name": "Repd (Ask City Hall)",
    "asset_type": ["chatbot"], "match_confidence": 1.0,
    "page_url": "https://www.cityofdenton.com/",
    "verification_status": "verified_observed",
}]


def test_feed_creates_discovered_asset():
    repo = _repo()
    _feed_inventory(repo, "City of Denton", _DETECTED)
    rows = repo.get_ai_assets(city="City of Denton")
    assert len(rows) == 1
    r = rows[0]
    assert r["asset_key"] == _asset_key("City of Denton", "repd")
    assert r["provenance"] == "discovered_scan"
    assert r["lifecycle_status"] == "discovered"
    assert r["presence"] == "active"
    assert r["first_observed_utc"]           # set on creation
    assert json.loads(r["asset_types_json"]) == ["chatbot"]


def test_feed_rescan_preserves_attestation_and_first_observed():
    repo = _repo()
    _feed_inventory(repo, "City of Denton", _DETECTED)
    first = repo.get_ai_assets()[0]["first_observed_utc"]
    # Human attests between scans.
    repo.upsert_ai_asset({"asset_key": _asset_key("City of Denton", "repd"),
                          "lifecycle_status": "attested",
                          "owner_email": "cio@denton.gov"})
    _feed_inventory(repo, "City of Denton", _DETECTED)   # re-scan
    r = repo.get_ai_assets()[0]
    assert r["lifecycle_status"] == "attested"
    assert r["owner_email"] == "cio@denton.gov"
    assert r["first_observed_utc"] == first, "first_observed must not move"


def test_feed_marks_vanished_asset_not_reobserved():
    repo = _repo()
    _feed_inventory(repo, "City of Denton", _DETECTED)
    _feed_inventory(repo, "City of Denton", [])   # next crawl: widget gone
    r = repo.get_ai_assets()[0]
    assert r["presence"] == "not_reobserved"
    assert r["lifecycle_status"] == "discovered", "feed must not auto-retire"


def test_feed_does_not_touch_declared_assets():
    repo = _repo(ai_assets=[{
        "asset_key": "city-of-denton::decl-abc12345", "city": "City of Denton",
        "provenance": "declared", "presence": "active",
        "lifecycle_status": "attested",
    }])
    _feed_inventory(repo, "City of Denton", [])
    r = repo.get_ai_assets()[0]
    assert r["presence"] == "active", "declared assets are not scan-observable"


# ── RBAC scoping (same filter_rows path the route uses) ───────────────────────

_ASSETS = [
    {"asset_key": "a::x", "city": "City of Denton"},
    {"asset_key": "b::y", "city": "City of Lewisville"},
]


def test_platform_admin_sees_all():
    repo = _repo(ai_assets=_ASSETS)
    principal = resolve_principal({"email": "chris@lewisville.com"}, repo) \
        if False else None
    # Platform admin path is bootstrapped via ADMIN_EMAILS env; emulate with
    # an all_cities principal directly through filter_rows semantics:
    from core.access import Principal, ROLE_PLATFORM_ADMIN
    p = Principal("admin@x", ROLE_PLATFORM_ADMIN, None, None, all_cities=True)
    assert len(filter_rows(repo.get_ai_assets(), p)) == 2


def test_agency_admin_scoped_to_grant():
    repo = _repo(
        ai_assets=_ASSETS,
        users=[{"email": "aa@denton.gov", "role": "agency_admin",
                "agency_id": "ag1"}],
        agencies=[{"id": "ag1", "name": "Denton",
                   "granted_cities": json.dumps(["City of Denton"])}],
    )
    p = resolve_principal({"email": "aa@denton.gov"}, repo)
    rows = filter_rows(repo.get_ai_assets(), p)
    assert [r["city"] for r in rows] == ["City of Denton"]
    assert p.can_see_city("City of Denton")
    assert not p.can_see_city("City of Lewisville")


def test_unknown_user_sees_nothing():
    repo = _repo(ai_assets=_ASSETS)
    p = resolve_principal({"email": "stranger@nowhere.com"}, repo)
    assert filter_rows(repo.get_ai_assets(), p) == []


# ── Standalone runner (sandbox has no pytest wheel) ───────────────────────────

if __name__ == "__main__":
    failures = 0
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_") and callable(v)}.items()):
        try:
            fn()
            print(f"  PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{'ALL TESTS PASSED' if not failures else f'{failures} FAILURE(S)'}")
    sys.exit(1 if failures else 0)
