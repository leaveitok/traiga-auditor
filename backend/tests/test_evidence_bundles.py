"""
test_evidence_bundles.py — audience-tailored evidence bundles (Phase 1).

Covers the PURE spec, the renderers, and the orchestrator/package assembly. Protects the
two doctrines the feature exists to uphold — provenance-first and candidate-not-verdict —
plus the tamper-evidence content hash that makes a bundle defensible.
"""
import io
import json
import zipfile
from pathlib import Path

import pytest

from engine.reporting import bundle_spec as bs, render_docx, render_pdf
from core.reporting import bundle_orchestrator as bo
from engine import rule_loader


def _schema():
    return rule_loader.load_schema()


def _presets():
    return _schema()["Report_Bundles"]["presets"]


DATA = {
    "scorecard": {"city": "City of Euless", "jurisdiction": "TX", "domain": "https://eulesstx.gov",
                  "traiga_status": "in_cure", "open_violations_count": 1, "min_days_remaining": 42,
                  "last_scanned_utc": "2026-07-20T09:00:00Z"},
    "ai_assets": [
        {"display_name": "Citibot", "asset_type": ["chatbot"], "provenance": "discovered_scan",
         "match_confidence": 0.95, "verification_status": "candidate", "page_url": "https://eulesstx.gov/"},
        {"display_name": "ChatGPT", "asset_type": ["genai_assistant"], "provenance": "discovered_oauth",
         "match_confidence": 1.0, "verification_status": "candidate"},
        {"display_name": "Granicus", "asset_type": ["automation"], "provenance": "declared",
         "match_confidence": 1.0, "verification_status": "confirmed"},
    ],
    "violations": [
        {"rule_id": "ETM-001", "citation": "Tex. Bus. & Com. Code §552.052", "severity": "high",
         "status": "in_cure", "first_observed_utc": "2026-07-01T00:00:00Z",
         "cure_deadline_utc": "2026-08-30T00:00:00Z", "days_remaining": 42, "vendor_id": "citibot",
         "evidence": {"page_url": "https://eulesstx.gov/", "matched_indicators": ["citibot-iframe"],
                      "remediation": "Add a conspicuous AI-use disclosure."}},
    ],
}


# ── Presets ──────────────────────────────────────────────────────────────────

def test_both_presets_present_and_shaped():
    p = _presets()
    assert "council_brief" in p and "ag_auditor_package" in p
    assert p["council_brief"]["package"] is False
    assert p["ag_auditor_package"]["package"] is True


# ── Provenance-first doctrine ────────────────────────────────────────────────

def test_provenance_summary_is_the_first_substantive_section():
    """The discovered-vs-declared page must lead, right after the cover. This is the
    doctrine that differentiates us from a self-attestation tool, so it is enforced in the
    engine and asserted here even if a preset were mis-ordered."""
    for key, preset in _presets().items():
        model = bs.build_bundle(DATA, preset)
        kinds = [s["kind"] for s in model["sections"]]
        non_cover = [k for k in kinds if k != "cover"]
        assert non_cover[0] == "provenance_summary", key


def test_provenance_summary_counts_discovered_vs_declared():
    sec = next(s for s in bs.build_bundle(DATA, _presets()["council_brief"])["sections"]
               if s["kind"] == "provenance_summary")
    assert sec["discovered_count"] == 2
    assert sec["declared_count"] == 1


@pytest.mark.parametrize("disc,decl,fragment", [
    (1, 0, "1 AI system was surfaced"),
    (2, 1, "2 were surfaced by automated discovery and 1 was declared"),
    (0, 1, "1 AI system is on record"),
])
def test_headline_grammar(disc, decl, fragment):
    """Executive-grade output: singular/plural agreement must be correct."""
    assets = ([{"display_name": f"D{i}", "provenance": "discovered_oauth"} for i in range(disc)] +
              [{"display_name": f"X{i}", "provenance": "declared"} for i in range(decl)])
    sec = next(s for s in bs.build_bundle({"scorecard": {"city": "T"}, "ai_assets": assets, "violations": []},
                                          _presets()["council_brief"])["sections"]
               if s["kind"] == "provenance_summary")
    assert fragment in sec["headline"]


# ── Candidate, not verdict ───────────────────────────────────────────────────

def test_bundles_frame_findings_as_candidates_not_determinations():
    blob = json.dumps(bs.build_bundle(DATA, _presets()["ag_auditor_package"]))
    assert "candidate" in blob.lower()
    assert "not enforcement determinations" in blob.lower()
    # Never assert a determination.
    assert "violation confirmed" not in blob.lower()


def test_full_preset_includes_methodology_and_attestation_summary_does_not():
    full = [s["kind"] for s in bs.build_bundle(DATA, _presets()["ag_auditor_package"])["sections"]]
    brief = [s["kind"] for s in bs.build_bundle(DATA, _presets()["council_brief"])["sections"]]
    assert "methodology" in full and "attestation" in full
    assert "methodology" not in brief and "attestation" not in brief


# ── Tamper-evidence ──────────────────────────────────────────────────────────

def test_content_hash_is_stable_across_time_and_version():
    """The hash identifies the FINDINGS, so it must not change with the timestamp or the
    tool release — that is what lets it detect a stale snapshot in Phase 2."""
    a = bs.build_bundle(DATA, _presets()["council_brief"], tool_release="01.4",
                        generated_utc="2026-01-01T00:00:00Z")["meta"]["content_sha256"]
    b = bs.build_bundle(DATA, _presets()["council_brief"], tool_release="99.9",
                        generated_utc="2026-12-31T23:59:59Z")["meta"]["content_sha256"]
    assert a == b and len(a) == 64


def test_content_hash_changes_when_findings_change():
    a = bs.build_bundle(DATA, _presets()["council_brief"])["meta"]["content_sha256"]
    d2 = json.loads(json.dumps(DATA))
    d2["ai_assets"].append({"display_name": "Otter.ai", "provenance": "discovered_oauth"})
    b = bs.build_bundle(d2, _presets()["council_brief"])["meta"]["content_sha256"]
    assert a != b


# ── Renderers ────────────────────────────────────────────────────────────────

def test_docx_renders_for_both_presets():
    """DOCX has no optional-dependency guard — always exercised."""
    for preset in _presets().values():
        model = bs.build_bundle(DATA, preset, tool_release="01.4")
        assert len(render_docx.render(model)) > 2000


def test_pdf_renders_for_both_presets():
    """PDF needs reportlab. It is imported LAZILY so the app boots without it; this test
    is skipped where reportlab is absent (e.g. a dev box that has not installed it yet)
    and runs for real in CI, which installs requirements.txt. reportlab-absent must never
    block the gate — the app degrades to a clean 'install reportlab' error, not a crash."""
    pytest.importorskip("reportlab")
    for preset in _presets().values():
        model = bs.build_bundle(DATA, preset, tool_release="01.4")
        assert render_pdf.render(model)[:4] == b"%PDF"


# ── Orchestrator + package ───────────────────────────────────────────────────

class _MockRepo:
    def get_scorecard(self):
        return [DATA["scorecard"]]
    def get_ai_assets(self, city=None):
        return [dict(a, asset_types=a["asset_type"]) for a in DATA["ai_assets"]]
    def get_violations(self):
        return [dict(v, city="City of Euless",
                     evidence_json=json.dumps(v["evidence"])) for v in DATA["violations"]]
    def get_audit_log(self, limit=100):
        return [{"timestamp_utc": "2026-07-20T09:00:00Z", "event": "scan_complete",
                 "details": {"city": "City of Euless", "summary": "Scan complete"}}]


def test_orchestrator_assembles_all_provenance_channels():
    data = bo.assemble_city_data(_MockRepo(), "City of Euless")
    provs = {a["provenance"] for a in data["ai_assets"]}
    assert {"discovered_scan", "discovered_oauth", "declared"} <= provs


def test_package_contains_pdf_docx_attachments_and_matching_manifest():
    pytest.importorskip("reportlab")  # build_package renders a PDF into the zip
    pkg = bo.build_package(_MockRepo(), "City of Euless", "ag_auditor_package", _schema(), tool_release="01.4")
    z = zipfile.ZipFile(io.BytesIO(pkg))
    names = z.namelist()
    assert any(n.endswith(".pdf") for n in names)
    assert any(n.endswith(".docx") for n in names)
    assert "attachments/inventory.csv" in names
    assert "MANIFEST.json" in names
    manifest = json.loads(z.read("MANIFEST.json"))
    # The manifest's hash must equal the model's content hash — the integrity anchor.
    model = bo.build_model(_MockRepo(), "City of Euless", "ag_auditor_package", _schema(), tool_release="01.4")
    assert manifest["content_sha256"] == model["meta"]["content_sha256"]


def test_inventory_csv_covers_every_provenance_channel():
    pytest.importorskip("reportlab")  # build_package renders a PDF into the zip
    pkg = bo.build_package(_MockRepo(), "City of Euless", "ag_auditor_package", _schema())
    csv_txt = zipfile.ZipFile(io.BytesIO(pkg)).read("attachments/inventory.csv").decode()
    assert "Discovered — website scan" in csv_txt
    assert "Discovered — OAuth / shadow AI" in csv_txt
    assert "Declared by city staff" in csv_txt


def test_missing_city_raises_lookup():
    with pytest.raises(LookupError):
        bo.assemble_city_data(_MockRepo(), "Nonexistent City")
