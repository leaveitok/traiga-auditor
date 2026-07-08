"""
test_safe_harbor.py — Municipal AI Profile derivation + attestation RBAC.

Standalone (stub repo, direct route-function calls; PYTHONPATH=tests/shims when
fastapi is absent). Contracts under test:
  - machine evaluators derive from existing platform data (no new pipeline)
  - attestation satisfies human controls; machine True satisfies machine controls
  - RBAC: platform_admin attests anywhere; agency_admin only their cities;
    viewers can read only their cities
  - readiness math: function scores + overall band
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone

from core.safeharbor import build_context, evaluate_profile
from engine.rule_loader import load_schema

MODULE = load_schema()["Safe_Harbor_Module"]
NOW = datetime.now(timezone.utc)
RECENT = NOW.isoformat()
STALE = (NOW - timedelta(days=45)).isoformat()


def _setup_admin(email="chris@test.gov"):
    from core import config
    config.ADMIN_EMAILS = [email]
    return email


class StubRepo:
    def __init__(self, scorecard=None, assets=None, violations=None,
                 audit_log=None, targets=None, users=None, agencies=None):
        self._scorecard = scorecard or []
        self._assets = assets or []
        self._violations = violations or []
        self._audit_log = audit_log or []
        self._targets = targets or []
        self._users = users or {}
        self._agencies = agencies or {}
        self.safe_harbor = []
        self.log_events = []

    def get_scorecard(self): return self._scorecard
    def get_targets(self): return self._targets
    def get_ai_assets(self, city=None):
        return [a for a in self._assets if not city or a.get("city") == city]
    def get_violations(self, status=None, city=None):
        return [v for v in self._violations if not city or v.get("city") == city]
    def get_audit_log(self, limit=100): return self._audit_log[-limit:]
    def get_user(self, email): return self._users.get(email)
    def get_agency(self, agency_id): return self._agencies.get(agency_id)
    def get_safe_harbor(self, city):
        return [r for r in self.safe_harbor if r["city"].lower() == city.lower()]
    def upsert_safe_harbor(self, record):
        self.safe_harbor = [r for r in self.safe_harbor
                            if (r["city"].lower(), r["control_id"]) !=
                               (record["city"].lower(), record["control_id"])]
        self.safe_harbor.append(dict(record)); return record
    def append_audit_log(self, **kw): self.log_events.append(kw)


def _healthy_ctx_repo(city="Lewisville"):
    return StubRepo(
        scorecard=[{"city": city, "traiga_status": "compliant", "last_scanned_utc": RECENT}],
        assets=[{"city": city, "asset_key": "a1", "attested_by": "cio@x.gov", "lifecycle_status": "active"}],
        violations=[{"city": city, "status": "cured", "cure_deadline_utc": RECENT}],
        audit_log=[{"event": "audit_completed", "timestamp_utc": RECENT}],
        targets=[{"city": city, "cloudflare_protected": "false"}],
    )


def test_machine_controls_derive_from_healthy_city():
    repo = _healthy_ctx_repo()
    result = evaluate_profile(MODULE, build_context(repo, "Lewisville"), [])
    by_id = {c["control_id"]: c for c in result["controls"]}
    for cid in ("SH-GOV-04", "SH-MAP-01", "SH-MAP-02", "SH-MAP-03",
                "SH-MEA-01", "SH-MEA-02", "SH-MAN-01", "SH-MAN-02"):
        assert by_id[cid]["status"] == "satisfied", f"{cid}: {by_id[cid]}"
        assert by_id[cid]["basis"] == "machine"
    # Human controls remain open without attestation
    for cid in ("SH-GOV-01", "SH-GOV-02", "SH-GOV-03", "SH-MAN-03", "SH-MAN-04"):
        assert by_id[cid]["status"] == "open"
    # Hybrid without Sentinel visibility -> attestation fallback, not failing
    assert by_id["SH-MEA-03"]["status"] == "open"


def test_unassessed_city_fails_machine_controls():
    repo = StubRepo(scorecard=[{"city": "Dallas", "traiga_status": "not_assessed",
                                "last_scanned_utc": ""}],
                    targets=[{"city": "Dallas"}])
    result = evaluate_profile(MODULE, build_context(repo, "Dallas"), [])
    by_id = {c["control_id"]: c for c in result["controls"]}
    assert by_id["SH-MAP-01"]["status"] == "failing"
    assert by_id["SH-MAP-03"]["status"] == "failing"
    assert result["band"] == "early"


def test_expired_violation_fails_remediation_control():
    repo = _healthy_ctx_repo()
    repo._violations.append({"city": "Lewisville", "status": "expired",
                             "cure_deadline_utc": STALE})
    result = evaluate_profile(MODULE, build_context(repo, "Lewisville"), [])
    by_id = {c["control_id"]: c for c in result["controls"]}
    assert by_id["SH-MAN-02"]["status"] == "failing"


def test_attestation_satisfies_and_band_improves():
    repo = _healthy_ctx_repo()
    atts = [{"city": "Lewisville", "control_id": cid, "status": "attested",
             "attested_by": "cio@x.gov", "attested_utc": RECENT, "notes": "n"}
            for cid in ("SH-GOV-01", "SH-GOV-02", "SH-GOV-03", "SH-MEA-03",
                        "SH-MAN-03", "SH-MAN-04")]
    result = evaluate_profile(MODULE, build_context(repo, "Lewisville"), atts)
    assert result["overall"]["satisfied"] == result["overall"]["total"]
    assert result["band"] == "ready"


def test_attest_rbac_agency_scoping():
    from fastapi import HTTPException
    from api.routes.safeharbor import attest_control, AttestBody
    _setup_admin("chris@test.gov")
    repo = _healthy_ctx_repo()
    repo._users = {
        "denton-admin@x.gov": {"email": "denton-admin@x.gov", "role": "agency_admin",
                               "agency_id": "ag1"},
    }
    repo._agencies = {"ag1": {"id": "ag1", "granted_cities": '["Denton"]'}}

    # platform admin: allowed anywhere
    rec = attest_control(city="Lewisville",
                         body=AttestBody(control_id="SH-GOV-01", status="attested", notes="CIO"),
                         repo=repo,
                         user={"email": "chris@test.gov", "uid": "u1"})
    assert rec["attested_by"] == "chris@test.gov"
    assert repo.get_safe_harbor("Lewisville")

    # agency admin for Denton: blocked on Lewisville
    try:
        attest_control(city="Lewisville",
                       body=AttestBody(control_id="SH-GOV-01"),
                       repo=repo,
                       user={"email": "denton-admin@x.gov", "uid": "u2"})
        raise AssertionError("expected 403")
    except HTTPException as exc:
        assert exc.status_code == 403


def test_attest_rejects_unknown_control():
    from fastapi import HTTPException
    from api.routes.safeharbor import attest_control, AttestBody
    admin = _setup_admin()
    repo = _healthy_ctx_repo()
    try:
        attest_control(city="Lewisville",
                       body=AttestBody(control_id="SH-NOPE-99"),
                       repo=repo, user={"email": admin, "uid": "u1"})
        raise AssertionError("expected 400")
    except HTTPException as exc:
        assert exc.status_code == 400
