"""
audit.py — Audit run trigger and status endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.

The audit engine (crawler, fingerprint, validator, cure period) is
completely storage-agnostic — it returns Python dicts which are then
persisted via the injected repository.
"""
from __future__ import annotations

import asyncio
import json
import traceback as _tb
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_current_user, is_admin
from core.dependencies import get_repository, limiter
from core.governance_service import GovernanceRepository
from core.scheduler import get_scheduler_state

router = APIRouter(prefix="/audit", tags=["audit"])


# ── In-memory run state (single-node; sufficient for beta) ───────────────────
_audit_state: Dict[str, Any] = {
    "status":            "idle",
    "started_utc":       None,
    "finished_utc":      None,
    "city_count":        0,
    "observed_failures": 0,
    "open_violations":   0,
    "error":             None,
}

DEMO_FIXTURES: Dict[str, Dict[str, Any]] = {
    "https://demo-compliant.example.gov/": {
        "city": "Demo Compliant City",
        "fixture": {
            "html": (
                "<html><body><h1>311 Services</h1>"
                "<div id='citibot-widget' class='citibot-chat'>"
                "<p>You are interacting with an AI system (virtual assistant).</p></div>"
                "<a href='/privacy-policy'>Privacy Policy</a>"
                "<script src='https://cdn.citibot.io/widget.js'></script>"
                "</body></html>"
            ),
            "script_hosts": ["cdn.citibot.io"],
            "text": "You are interacting with an AI system (virtual assistant). Privacy Policy.",
            "cookie_names": ["citibot_session"],
        },
    },
    "https://demo-noncompliant.example.gov/": {
        "city": "Demo NonCompliant City",
        "fixture": {
            "html": (
                "<html><body><h1>Resident Help</h1>"
                "<div class='chatbot' data-civicplus='1'>Ask our assistant</div>"
                "<script src='https://assets.civicplus.com/chat.js'></script>"
                "</body></html>"
            ),
            "script_hosts": ["assets.civicplus.com"],
            "text": "Resident Help. Ask our assistant.",
            "cookie_names": ["civicplus_id"],
        },
    },
}


class AuditRunResponse(BaseModel):
    status:            str
    started_utc:       Optional[str]
    finished_utc:      Optional[str]
    city_count:        int
    observed_failures: int
    open_violations:   int
    error:             Optional[str]
    # Real-time progress: {"current_city": str, "completed": int, "total": int}
    progress:          Optional[Dict[str, Any]] = None


class ChromeCapture(BaseModel):
    """
    PageCapture data collected by a real Chrome browser (bypasses Cloudflare).
    POST to /audit/chrome-capture to inject a browser-collected capture into
    the fingerprint engine and get back detected AI assets.

    Set persist=True to also run disclosure validation and update the
    scorecard + violations in the repository (requires city/jurisdiction/domain).
    """
    url:           str
    html:          str = ""
    script_hosts:  List[str] = []
    js_globals:    List[str] = []
    iframe_origins: List[str] = []
    cookie_names:  List[str] = []
    network_urls:  List[str] = []
    text:          str = ""
    # Persist mode — write violations + scorecard to repo
    persist:       bool = False
    city:          Optional[str] = None
    jurisdiction:  str = "TX"
    domain:        Optional[str] = None


class ChromeCaptureResponse(BaseModel):
    url:             str
    detected_assets: List[Dict[str, Any]]
    match_threshold: float
    persisted:       bool = False
    open_violations: int = 0


async def _run_audit_task(
    targets: List[Dict[str, Any]],
    demo: bool,
    repo: GovernanceRepository,
) -> None:
    """
    Background wrapper: sets _audit_state, delegates to engine.pipeline.run_full_audit,
    then records completion or error.  All internal detail stays server-side.
    """
    global _audit_state
    _audit_state["status"]       = "running"
    _audit_state["started_utc"]  = datetime.now(timezone.utc).isoformat()
    _audit_state["finished_utc"] = None
    _audit_state["error"]        = None
    _audit_state["progress"]     = {"current_city": "", "completed": 0,
                                    "total": len(targets)}

    def _on_progress(p: Dict[str, Any]) -> None:
        # Called from the executor thread; plain dict assignment is atomic
        # enough for a monotonic status readout.
        _audit_state["progress"] = p

    try:
        from engine.pipeline import run_full_audit
        fixtures = DEMO_FIXTURES if demo else None
        loop     = asyncio.get_event_loop()
        result   = await loop.run_in_executor(
            None, lambda: run_full_audit(targets, repo, fixtures,
                                         progress_cb=_on_progress)
        )
        _audit_state.update({
            "status":       "completed",
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            **result,
        })
    except Exception as exc:
        ref = str(uuid.uuid4())[:8]
        tb  = _tb.format_exc()
        print(f"[audit_task] ERROR [{ref}] {type(exc).__name__}: {exc}\n{tb}")
        _audit_state["status"]          = "error"
        _audit_state["error"]           = f"Audit pipeline error. Reference ID: {ref}"
        _audit_state["last_traceback"]  = f"[{ref}] {type(exc).__name__}: {exc}\n{tb}"
        _audit_state["finished_utc"]    = datetime.now(timezone.utc).isoformat()


@router.post("/run", response_model=AuditRunResponse)
@limiter.limit("5/minute")
async def trigger_audit(
    request: Request,
    background_tasks: BackgroundTasks,
    demo: bool = False,
    city_filter: Optional[str] = None,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    if _audit_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Audit already running")

    # City-scoped users can only audit their assigned city
    if not is_admin(user["email"]):
        user_row = repo.get_user(user["email"])
        if not user_row or not user_row.get("city"):
            raise HTTPException(
                status_code=403,
                detail="No city assigned to your account. Contact your administrator."
            )
        city_filter = user_row["city"]

    if demo:
        targets = [
            {"url": k, "city": v["city"], "jurisdiction": "TX", "domain": k}
            for k, v in DEMO_FIXTURES.items()
        ]
    else:
        targets = repo.get_targets()
        if city_filter:
            # Individual re-audit: always scan the requested city (this is the
            # only path that re-scrapes a proxy city — e.g. to update its status
            # or confirm a fix). Proxy cost is incurred deliberately, one city.
            targets = [t for t in targets if t.get("city") == city_filter]
        else:
            # Bulk "Run Audit": skip proxy (ScraperAPI / cloudflare_protected)
            # cities that ALREADY have an open violation. Once a paid-scrape city
            # is confirmed positive, it is only re-scanned on demand (individual
            # re-audit), never in the recurring bulk run — this is the ScraperAPI
            # cost control. Free (Playwright) cities and not-yet-flagged proxy
            # cities remain in the bulk run so violations can still be discovered
            # and cure clocks keep advancing.
            def _is_proxy(t: Dict[str, Any]) -> bool:
                return str(t.get("cloudflare_protected", "")).strip().lower() in ("true", "1", "yes")
            try:
                open_v = repo.get_violations()
                cities_with_open = {v.get("city") for v in open_v
                                    if str(v.get("status", "")).lower() != "cured"}
            except Exception:
                cities_with_open = set()
            targets = [t for t in targets
                       if not (_is_proxy(t) and t.get("city") in cities_with_open)]
        if not targets:
            raise HTTPException(status_code=400, detail="No active targets found for this city")

    background_tasks.add_task(_run_audit_task, targets, demo, repo)
    try:
        repo.append_audit_log(
            event="audit_triggered", city_count=len(targets), failures=0,
            details={
                "actor":   user.get("email", "unknown"),
                "summary": (f"Scan started for {city_filter}" if city_filter
                            else f"Full scan started ({len(targets)} cities)"),
                "scope":   city_filter or "all",
                "demo":    demo,
            })
    except Exception as exc:
        print(f"[activity] WARN: could not log audit_triggered: {exc}")
    return AuditRunResponse(status="started", **{
        k: _audit_state[k] for k in AuditRunResponse.model_fields if k != "status"
    })


@router.get("/run", response_model=AuditRunResponse)
def get_audit_status():
    return AuditRunResponse(**_audit_state)


@router.get("/trace")
def get_audit_trace(user: dict = Depends(get_current_user)):
    """Admin-only: return the raw traceback from the last failed audit run."""
    if not is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admin only")
    return {
        "status":         _audit_state.get("status"),
        "error":          _audit_state.get("error"),
        "last_traceback": _audit_state.get("last_traceback"),
        "started_utc":    _audit_state.get("started_utc"),
        "finished_utc":   _audit_state.get("finished_utc"),
    }


@router.get("/schedule")
def get_schedule_status(
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Return automated scan schedule state.

    auto_scan_cities:   targets that will be scanned automatically.
    manual_scan_cities: Cloudflare-protected targets that require manual Deep Scan.
    """
    targets       = repo.get_targets()
    auto_count    = sum(1 for t in targets if not t.get("cloudflare_protected", False))
    manual_count  = sum(1 for t in targets if t.get("cloudflare_protected", False))
    manual_cities = [t["city"] for t in targets if t.get("cloudflare_protected", False)]

    state = get_scheduler_state()
    return {
        **state,
        "auto_scan_cities":   auto_count,
        "manual_scan_cities": manual_count,
        "manual_city_names":  manual_cities,
    }


@router.post("/chrome-capture", response_model=ChromeCaptureResponse)
@limiter.limit("10/minute")
def chrome_capture(
    request: Request,
    body: ChromeCapture,
):
    """
    Accept a PageCapture collected by a real Chrome browser (for sites that
    block headless Playwright via Cloudflare/WAF) and run it through the
    fingerprint engine immediately.

    With persist=True also runs disclosure validation and writes violations +
    scorecard to the repository.  Requires city, jurisdiction, and domain fields.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    from engine import rule_loader
    from engine.crawler import PageCapture
    from engine.fingerprint_engine import fingerprint
    from engine.disclosure_validator import validate

    schema    = rule_loader.load_schema()
    vendors   = rule_loader.get_vendors(schema)
    threshold = rule_loader.get_match_threshold(schema)
    rules     = rule_loader.get_external_rules(schema)

    cap = PageCapture(
        url=body.url,
        html=body.html,
        script_hosts=body.script_hosts,
        js_globals=body.js_globals,
        iframe_origins=body.iframe_origins,
        cookie_names=body.cookie_names,
        network_urls=body.network_urls,
        text=body.text,
        render_engine="chrome_mcp",
    )
    assets = fingerprint(cap, vendors, threshold)
    asset_dicts = [
        {
            "vendor_id":           a.vendor_id,
            "display_name":        a.display_name,
            "asset_type":          a.asset_types,
            "match_confidence":    a.match_confidence,
            "matched_indicators":  a.matched_indicators,
            "page_url":            a.page_url,
            "verification_status": a.verification_status,
        }
        for a in assets
    ]

    if not body.persist:
        return ChromeCaptureResponse(
            url=body.url,
            detected_assets=asset_dicts,
            match_threshold=threshold,
        )

    # ── Persist mode: run validation → reconcile → write scorecard/violations ──
    if not body.city:
        raise HTTPException(status_code=400, detail="city is required when persist=True")

    from engine.cure_period import reconcile, open_violations
    from engine.scorecard import build_city_row

    city   = body.city
    domain = body.domain or body.url
    repo   = get_repository()   # singleton — safe to call directly here

    try:
        # Only read violations for this city — O(1 Sheets read) regardless of
        # total violation count.  Preserved (other-city) violations are never
        # rewritten here, so we avoid the O(N×2) API-call storm that blows
        # through the Sheets 60 reads/min/user quota when N >= 30.
        scoped_violations = repo.get_violations(city=city)

        state: Dict[str, Any] = {"violations": {}}
        for v in scoped_violations:
            vid = v.get("violation_id", "")
            if vid:
                raw_ev = v.get("evidence_json") or "{}"
                try:
                    evidence = json.loads(raw_ev)
                except (json.JSONDecodeError, TypeError, ValueError):
                    evidence = {}
                state["violations"][vid] = {
                    **v,
                    "evidence":           evidence,
                    "cure_period_status": v.get("cure_period_status", "True") == "True",
                    "needs_human_review": v.get("needs_human_review", "True") == "True",
                }

        observed_failures: List[Dict[str, Any]] = []
        for a in assets:
            for v in validate(cap, a, rules):
                observed_failures.append({
                    "city":      city,
                    "domain":    domain,
                    "asset_id":  a.asset_id,
                    "vendor_id": a.vendor_id,
                    "rule_id":   v["rule_id"],
                    "citation":  v["citation"],
                    "severity":  v["severity"],
                    "evidence": {
                        "page_url":           a.page_url,
                        "matched_indicators": a.matched_indicators,
                        "remediation":        v["remediation"],
                    },
                })

        scorecard_cfg = schema["scorecard_schema"]
        # Chrome capture = successful scan of this city; pass crawled_cities so
        # reconcile() can safely cure violations that no longer reproduce.
        state     = reconcile(state, observed_failures, crawled_cities={city})
        all_open  = open_violations(state)
        city_open = [v for v in all_open if v["city"] == city]

        row = build_city_row(
            city=city,
            jurisdiction=body.jurisdiction,
            domain=domain,
            assets=asset_dicts,
            open_violations=city_open,
            scorecard_cfg=scorecard_cfg,
        )

        # write_scorecard_rows uses _upsert_by_key — writes only this city's
        # row (insert or update).  No need to read+rewrite all other cities.
        repo.write_scorecard_rows([row])
        # Same pattern for violations: write only this city's updated records.
        # Preserved (other-city) violations are already correct in Sheets and
        # must not be re-written (that would cause another 60+/min API storm).
        repo.write_violations(list(state["violations"].values()))
        repo.append_audit_log(
            event="chrome_capture",
            city_count=1,
            failures=len(observed_failures),
            details={"city": city, "open_violations": len(city_open)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        # Log full detail server-side only — never expose internal state to client
        ref = str(uuid.uuid4())[:8]
        print(f"[chrome_capture] ERROR [{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}")
        _audit_state["last_traceback"] = f"[chrome_capture:{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}"
        raise HTTPException(
            status_code=500,
            detail=f"An internal error occurred. Reference ID: {ref}",
        )

    return ChromeCaptureResponse(
        url=body.url,
        detected_assets=asset_dicts,
        match_threshold=threshold,
        persisted=True,
        open_violations=len(city_open),
    )
