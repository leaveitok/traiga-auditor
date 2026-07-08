"""
test_sentinel_feed.py — Sentinel telemetry → inventory feed (Gap 3).

Contracts:
  - events group by (city, site) into discovered_sentinel usage assets
  - untagged events are skipped fail-secure, never guessed into a city
  - merge-preserving upsert: re-sync never clobbers human fields
  - SH-MEA-03 (employee AI visibility) flips machine-true once usage assets exist
  - RBAC: sync is platform_admin only
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone

from core.sentinel_feed import build_usage_assets, sync_to_inventory

NOW = datetime.now(timezone.utc).isoformat()

EVENTS = [
    {"city": "Lewisville", "site_id": "chatgpt", "policy_id": "PII-SSN", "action": "block",
     "device_id": "d1", "timestamp_utc": NOW},
    {"city": "Lewisville", "site_id": "chatgpt", "policy_id": "PII-SSN", "action": "warn",
     "device_id": "d2", "timestamp_utc": NOW},
    {"city": "Lewisville", "site_id": "claude", "policy_id": "CJIS", "action": "block",
     "device_id": "d1", "timestamp_utc": NOW},
    {"city": "Denton", "site_id": "gemini", "policy_id": "HIPAA", "action": "warn",
     "device_id": "d9", "timestamp_utc": NOW},
    {"city": "", "site_id": "chatgpt", "policy_id": "PII-SSN", "action": "block",
     "device_id": "dX", "timestamp_utc": NOW},          # untagged -> skipped
]
HEARTBEATS = [
    {"city": "Lewisville", "device_id": "d1"}, {"city": "Lewisville", "device_id": "d2"},
    {"city": "Lewisville", "device_id": "d3"}, {"city": "Denton", "device_id": "d9"},
]


def test_grouping_counts_and_failsecure_skip():
    built = build_usage_assets(EVENTS, HEARTBEATS)
    assert built["skipped_untagged"] == 1
    assert built["cities"] == ["Denton", "Lewisville"]
    by_key = {a["asset_key"]: a for a in built["assets"]}
    gpt = by_key["sentinel:chatgpt@Lewisville"]
    assert gpt["provenance"] == "discovered_sentinel"
    assert gpt["display_name"].startswith("ChatGPT")
    assert gpt["sentinel_event_count"] == "2"
    assert gpt["sentinel_blocked_count"] == "1"
    assert gpt["sentinel_device_count"] == "2"
    assert gpt["sentinel_fleet_devices"] == "3"
    assert "sentinel:claude@Lewisville" in by_key
    assert "sentinel:gemini@Denton" in by_key


class StubSentinelRepo:
    def get_events(self, policy_id=None, user_id=None, limit=200): return EVENTS
    def get_heartbeats(self, limit=500): return HEARTBEATS


class StubGovRepo:
    """Reimplements the merge-preserving upsert contract."""
    def __init__(self):
        self.assets = {}
        self.log = []
    def upsert_ai_asset(self, asset):
        key = asset["asset_key"]
        existing = self.assets.get(key, {})
        merged = {**existing, **{k: v for k, v in asset.items() if v is not None}}
        self.assets[key] = merged
        return merged
    def append_audit_log(self, **kw): self.log.append(kw)


def test_sync_writes_and_resync_preserves_human_fields():
    gov = StubGovRepo()
    r1 = sync_to_inventory(gov, StubSentinelRepo())
    assert r1["synced"] == 3 and r1["errors"] == []
    assert r1["skipped_untagged_events"] == 1
    # A human attests the ChatGPT usage asset (owner + purpose + CID field)
    key = "sentinel:chatgpt@Lewisville"
    gov.assets[key].update({"owner_email": "cio@lewisville.gov",
                            "purpose": "Staff drafting aid",
                            "cid_limitations": "No PII per policy",
                            "lifecycle_status": "attested"})
    # Re-sync: machine fields refresh, human fields survive
    r2 = sync_to_inventory(gov, StubSentinelRepo())
    assert r2["synced"] == 3
    a = gov.assets[key]
    assert a["owner_email"] == "cio@lewisville.gov"
    assert a["purpose"] == "Staff drafting aid"
    assert a["cid_limitations"] == "No PII per policy"
    assert a["lifecycle_status"] == "attested"
    assert a["sentinel_event_count"] == "2"


def test_safeharbor_mea03_flips_with_sentinel_assets():
    from core.safeharbor import _sentinel_active
    ctx_without = {"assets": [{"provenance": "discovered_scan"}], "sentinel_devices": None}
    assert _sentinel_active(ctx_without) is None
    ctx_with = {"assets": [{"provenance": "discovered_sentinel",
                            "last_observed_utc": NOW}], "sentinel_devices": None}
    assert _sentinel_active(ctx_with) is True


def test_sync_route_rbac():
    from fastapi import HTTPException
    from api.routes.inventory import sync_sentinel_usage
    from core import config
    config.ADMIN_EMAILS = ["chris@test.gov"]

    class GovWithUsers(StubGovRepo):
        def get_user(self, email): return None
        def get_agency(self, agency_id): return None

    gov = GovWithUsers()
    ok = sync_sentinel_usage(user={"email": "chris@test.gov", "uid": "u1"},
                             repo=gov, sentinel_repo=StubSentinelRepo())
    assert ok["synced"] == 3
    assert any(e.get("event") == "sentinel_usage_synced" for e in gov.log)
    try:
        sync_sentinel_usage(user={"email": "viewer@denton.gov", "uid": "u2"},
                            repo=gov, sentinel_repo=StubSentinelRepo())
        raise AssertionError("expected 403")
    except HTTPException as exc:
        assert exc.status_code == 403
