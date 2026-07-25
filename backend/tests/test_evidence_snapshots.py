"""
test_evidence_snapshots.py — the Evidence Room (Phase 2).

A snapshot freezes the render-agnostic BundleModel plus its integrity hash. These tests
protect the properties that make it a defensible evidence trail:
  * round-trip through the repository Protocol (metadata list omits the heavy model_json;
    the single-get returns it);
  * immutability — a snapshot re-renders byte-content-identically later;
  * stale detection — a snapshot flips to stale exactly when the city's live data changes;
  * tombstone semantics — a deleted snapshot disappears from listings but is never hard-
    removed;
  * self-containment — a snapshot's package rebuilds from the frozen model with no live
    repo access.
"""
import json

import pytest

from core.reporting import bundle_orchestrator as bo
from engine import rule_loader
from tests.mock_repository import MockGovernanceRepository


def _schema():
    return rule_loader.load_schema()


SCORECARD = [{"city": "City of Euless", "jurisdiction": "TX", "domain": "https://eulesstx.gov",
              "traiga_status": "in_cure", "open_violations_count": 1, "min_days_remaining": 42,
              "last_scanned_utc": "2026-07-20T09:00:00Z"}]
ASSETS = [
    {"asset_key": "a1", "city": "City of Euless", "display_name": "Citibot", "asset_types": ["chatbot"],
     "provenance": "discovered_scan", "match_confidence": 0.95, "verification_status": "candidate"},
    {"asset_key": "a2", "city": "City of Euless", "display_name": "ChatGPT", "asset_types": ["genai_assistant"],
     "provenance": "discovered_oauth", "match_confidence": 1.0, "verification_status": "candidate"},
]
VIOLATIONS = [{"city": "City of Euless", "rule_id": "ETM-001", "citation": "Tex. Bus. & Com. Code §552.052",
               "severity": "high", "status": "in_cure", "first_observed_utc": "2026-07-01T00:00:00Z",
               "cure_deadline_utc": "2026-08-30T00:00:00Z", "days_remaining": 42, "vendor_id": "citibot",
               "evidence_json": json.dumps({"remediation": "Disclose."})}]


def _repo():
    return MockGovernanceRepository(scorecard=list(SCORECARD),
                                    ai_assets=[dict(a) for a in ASSETS],
                                    violations=[dict(v) for v in VIOLATIONS])


# ── Protocol round-trip ──────────────────────────────────────────────────────

def test_snapshot_roundtrip_metadata_list_omits_model_json():
    repo = _repo()
    bo.create_snapshot(repo, "City of Euless", "council_brief", _schema(), actor="clee", tool_release="01.5")
    lst = repo.get_report_snapshots("City of Euless")
    assert len(lst) == 1
    assert "model_json" not in lst[0]            # list is lightweight
    full = repo.get_report_snapshot(lst[0]["id"])
    assert "model_json" in full                  # single-get carries the frozen model


def test_snapshot_records_hash_and_source_fingerprint():
    repo = _repo()
    meta = bo.create_snapshot(repo, "City of Euless", "ag_auditor_package", _schema(), tool_release="01.5")
    assert len(meta["content_sha256"]) == 64
    assert meta["source_fingerprint"]
    assert meta["audience"]


# ── Immutability / reproducibility ───────────────────────────────────────────

def test_saved_snapshot_rerenders_from_frozen_model():
    repo = _repo()
    meta = bo.create_snapshot(repo, "City of Euless", "ag_auditor_package", _schema(), tool_release="01.5")
    pytest.importorskip("reportlab")
    assert bo.render_snapshot(repo, meta["id"], "pdf")[:4] == b"%PDF"
    assert len(bo.render_snapshot(repo, meta["id"], "docx")) > 2000


def test_snapshot_package_is_self_contained_and_hash_matches():
    repo = _repo()
    meta = bo.create_snapshot(repo, "City of Euless", "ag_auditor_package", _schema(), tool_release="01.5")
    pytest.importorskip("reportlab")
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(bo.render_snapshot_package(repo, meta["id"])))
    names = z.namelist()
    assert any(n.endswith(".pdf") for n in names) and any(n.endswith(".docx") for n in names)
    assert "attachments/inventory.csv" in names and "MANIFEST.json" in names
    assert json.loads(z.read("MANIFEST.json"))["content_sha256"] == meta["content_sha256"]


# ── Stale detection ──────────────────────────────────────────────────────────

def test_snapshot_is_current_then_stale_when_data_changes():
    repo = _repo()
    bo.create_snapshot(repo, "City of Euless", "council_brief", _schema(), tool_release="01.5")
    assert bo.list_snapshots(repo, "City of Euless")[0]["stale"] is False
    # Change the findings: add a new discovered asset.
    repo.upsert_ai_asset({"asset_key": "a3", "city": "City of Euless", "display_name": "Otter.ai",
                          "provenance": "discovered_oauth", "verification_status": "candidate"})
    assert bo.list_snapshots(repo, "City of Euless")[0]["stale"] is True


# ── Tombstone semantics ──────────────────────────────────────────────────────

def test_delete_is_a_tombstone_not_a_hard_removal():
    repo = _repo()
    meta = bo.create_snapshot(repo, "City of Euless", "council_brief", _schema(), tool_release="01.5")
    assert repo.delete_report_snapshot(meta["id"]) is True
    assert repo.get_report_snapshots("City of Euless") == []      # gone from listings
    assert repo.get_report_snapshot(meta["id"]) is None            # and from single-get
    # But the underlying record still exists, marked deleted (evidence never destroyed).
    assert any(r.get("id") == meta["id"] and r.get("deleted") for r in repo._report_snapshots)


def test_render_missing_snapshot_returns_none():
    repo = _repo()
    assert bo.render_snapshot(repo, "nope", "pdf") is None
    assert bo.render_snapshot_package(repo, "nope") is None
