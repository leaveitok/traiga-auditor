"""
test_bulk_import.py — unit tests for POST /api/targets/bulk (platform_admin only).

Calls the route function directly with a stub repo so the tests run standalone
in the sandbox (no fastapi TestClient required). RBAC contract:
  - platform_admin (ADMIN_EMAILS) → import allowed
  - anyone else → 403 (agencies own cities one at a time; bulk is operator-only)
Import must NEVER trigger scans — it only creates targets + not_assessed rows.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _setup_admin_email(email="chris@test.gov"):
    from core import config
    config.ADMIN_EMAILS = [email]
    return email


class StubRepo:
    """Minimal GovernanceRepository stand-in for the bulk route."""
    def __init__(self, targets=None):
        self.targets = targets or []
        self.scorecard_rows = []
        self.log_events = []

    def get_targets(self):
        return self.targets

    def add_target(self, city, jurisdiction, domain, url, tags, cloudflare_protected):
        t = {"id": str(len(self.targets) + 1), "city": city, "jurisdiction": jurisdiction,
             "domain": domain, "url": url, "tags": tags,
             "cloudflare_protected": cloudflare_protected, "active": True}
        self.targets.append(t)
        return t

    def write_scorecard_rows(self, rows):
        self.scorecard_rows.extend(rows)

    def append_audit_log(self, **kw):
        self.log_events.append(kw)

    # resolve_principal probes user records; None = unknown → viewer w/ no cities
    def get_user(self, email):
        return None

    def get_agency(self, agency_id):
        return None


def _run_bulk(repo, user_email, rows):
    from api.routes.targets import bulk_import_targets, BulkImportRequest
    body = BulkImportRequest(rows=rows)
    user = {"uid": "u1", "email": user_email, "role": None, "city": None}
    return bulk_import_targets(body=body, repo=repo, user=user)


def test_admin_imports_and_dedupes():
    admin = _setup_admin_email()
    repo = StubRepo(targets=[{"id": "1", "city": "Lewisville", "domain": "cityoflewisville.com"}])
    result = _run_bulk(repo, admin, rows=[
        {"city": "Grand Prairie", "domain": "https://www.gptx.org/Home"},   # good; normalized
        {"city": "Lewisville",    "domain": "cityoflewisville.com"},        # dup city
        {"city": "Nowhere",       "domain": "not-a-domain"},                # invalid domain
        {"city": "Denton Clone",  "domain": "WWW.GPTX.ORG"},                # dup domain of row 1
    ])
    assert result["added"] == 1
    assert result["added_cities"] == ["Grand Prairie"]
    assert len(result["skipped"]) == 3
    reasons = " | ".join(s["reason"] for s in result["skipped"])
    assert "duplicate city" in reasons and "invalid" in reasons and "duplicate domain" in reasons
    # Domain normalized: scheme, path, www stripped
    gp = [t for t in repo.targets if t["city"] == "Grand Prairie"][0]
    assert gp["domain"] == "gptx.org"
    assert gp["url"] == "https://gptx.org"
    # Placeholder scorecard row written as not_assessed (instant dashboard visibility)
    assert repo.scorecard_rows and repo.scorecard_rows[0]["traiga_status"] == "not_assessed"
    # Activity logged
    assert any(e.get("event") == "targets_bulk_imported" for e in repo.log_events)


def test_non_admin_gets_403():
    from fastapi import HTTPException
    _setup_admin_email("chris@test.gov")
    repo = StubRepo()
    try:
        _run_bulk(repo, "agency-user@denton.gov", rows=[{"city": "X", "domain": "x.gov"}])
        raise AssertionError("expected HTTPException(403)")
    except HTTPException as exc:
        assert exc.status_code == 403
    assert repo.targets == []          # nothing written
    assert repo.scorecard_rows == []   # nothing written


def test_empty_and_oversize_rejected():
    from fastapi import HTTPException
    admin = _setup_admin_email()
    repo = StubRepo()
    for rows in ([], [{"city": f"C{i}", "domain": f"c{i}.gov"} for i in range(2001)]):
        try:
            _run_bulk(repo, admin, rows=rows)
            raise AssertionError("expected HTTPException(400)")
        except HTTPException as exc:
            assert exc.status_code == 400
