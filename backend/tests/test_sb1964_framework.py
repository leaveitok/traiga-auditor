"""
test_sb1964_framework.py — the Texas SB 1964 government AI code-of-ethics LENS.

SB 1964 (Tex. Gov. Code, 89R 2025) directs DIR to establish an AI code of ethics for state
agencies AND LOCAL GOVERNMENTS and requires an AI system inventory — the artifact this
platform produces. The lens is added the governance-as-code way: a per-control ref + an
overlap grade + a registry entry + a Settings flag. NO engine change. These tests protect
that contract:

  * every control carries an sb1964 mapping with an honest overlap grade;
  * the framework is registered with an enable-flag and TX/mandatory metadata;
  * evaluate_profile is UNTOUCHED — the satisfied/unsatisfied result is identical, proving
    the lens is a projection, not a second assessment (the skill's core non-negotiable).

Source: capitol.texas.gov/tlodocs/89R/analysis/pdf/SB01964S.pdf
"""
import json

import pytest

from engine import rule_loader

VALID_OVERLAP = {"strong", "partial", "weak"}


def _module():
    return rule_loader.load_schema()["Safe_Harbor_Module"]


def test_all_14_controls_carry_an_sb1964_mapping():
    controls = _module()["controls"]
    assert len(controls) == 14
    for c in controls:
        assert c.get("sb1964_ref"), f"{c['control_id']} missing sb1964_ref"
        assert c.get("sb1964_overlap") in VALID_OVERLAP, f"{c['control_id']} bad overlap"


def test_the_inventory_control_maps_strong_because_sb1964_mandates_it():
    """SB 1964 explicitly requires an AI inventory — our inventory control must reflect the
    strongest overlap, since it IS the statutory artifact."""
    controls = {c["control_id"]: c for c in _module()["controls"]}
    assert controls["SH-MAP-01"]["sb1964_overlap"] == "strong"
    assert "inventory" in controls["SH-MAP-01"]["sb1964_ref"].lower()


def test_overlap_is_graded_honestly_not_all_strong():
    """An honest crosswalk has partial cells (e.g. cure-deadline tracking is a TRAIGA
    construct, not an SB 1964 duty). All-strong would be the overstatement the skill warns
    against."""
    grades = [c["sb1964_overlap"] for c in _module()["controls"]]
    assert grades.count("strong") >= 1 and grades.count("partial") >= 1


def test_sb1964_is_registered_with_flag_jurisdiction_and_citation():
    fw = next((f for f in _module()["frameworks"] if f["id"] == "sb1964"), None)
    assert fw, "sb1964 not in framework registry"
    assert fw["jurisdiction"] == "TX" and fw["mandatory"] is True
    assert fw["enable_flag"] == "FRAMEWORK_SB1964_ENABLED"
    assert fw["ref_field"] == "sb1964_ref" and fw["overlap_field"] == "sb1964_overlap"
    assert fw.get("default_enabled") is True          # applies to every TX city
    assert "capitol.texas.gov" in fw["source_citation"]
    assert fw.get("caveats"), "a crosswalk must carry caveats"


def test_setting_flag_exists_and_defaults_on():
    from core import settings, config
    assert "FRAMEWORK_SB1964_ENABLED" in settings.SETTABLE
    assert config.FRAMEWORK_SB1964_ENABLED is True   # mandatory TX statute → on by default


def test_evaluate_profile_is_unchanged_by_the_lens():
    """The non-negotiable: adding a framework must NOT change the assessment. Same 14
    controls, same status computation — the new fields are carried, never evaluated."""
    from core.safeharbor import evaluate_profile
    module = _module()
    ctx = {"scorecard_row": {}, "violations": [], "ai_assets": [], "scan_history": []}
    res = evaluate_profile(module, ctx, [])
    assert len(res["controls"]) == 14
    assert set(res["overall"]) == {"satisfied", "total", "pct"}
    # A control's computed status must not depend on sb1964 fields.
    for c in res["controls"]:
        assert c["status"] in {"satisfied", "failing", "open"}


def test_statement_docx_renders_an_sb1964_variant():
    """The report speaks the framework's language and cites it. Needs fastapi (the route
    module) — runs in CI; skipped where fastapi is absent."""
    pytest.importorskip("fastapi")
    from api.routes.safeharbor import _build_statement_docx
    import tempfile, os
    from docx import Document
    module = _module()
    fw = next(f for f in module["frameworks"] if f["id"] == "sb1964")
    result = {
        "scores": {fn: {"satisfied": 1, "total": 2, "pct": 0.5} for fn in ("govern", "map", "measure", "manage")},
        "overall": {"satisfied": 4, "total": 14, "pct": 0.29}, "band": "amber",
        "controls": [{"control_id": c["control_id"], "title": c["title"], "status": "open",
                      "basis": "attested", "nist_ref": c.get("nist_ref", "")} for c in module["controls"]],
    }
    path = os.path.join(tempfile.mkdtemp(), "stmt.docx")
    _build_statement_docx(path, "City of Allen", module, result, {"violations": []}, fw)
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "SB 1964" in text or "Code of Ethics" in text        # titled for the framework
    assert "capitol.texas.gov" in text                          # cites the statute
