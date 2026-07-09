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

from core import config
from core import run_state as _rs
from core.access import resolve_principal, scope_requested_cities
from core.auth import get_current_user, is_admin
from core.dependencies import get_repository, limiter
from core.governance_service import GovernanceRepository
from core.scheduler import get_scheduler_state

router = APIRouter(prefix="/audit", tags=["audit"])


# ── Durable, cross-instance run state ────────────────────────────────────────
# Run status/progress lives in the datastore (via the repository), NOT in a
# module global, so every Cloud Run instance agrees on it. See core/run_state.py
# for the full rationale (multi-instance status drift, the per-process 409 race,
# fresh-instance 500s, and the session-affinity auth symptom this removes).
# The default idle template comes from _rs.default_audit_state().

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
    Background wrapper: writes durable run state through the repository,
    delegates to engine.pipeline.run_full_audit, then records completion or
    error. Every write refreshes heartbeat_utc so the run's lease stays alive
    while it is making progress. All internal detail stays server-side.

    The slot has already been claimed (status='running') by the trigger; this
    task keeps started_utc consistent with that claim.
    """
    total   = len(targets)
    base    = repo.get_run_state(_rs.AUDIT_KEY) or {}
    started = base.get("started_utc") or _rs.now_iso()

    def _write_running(progress: Optional[Dict[str, Any]]) -> None:
        state = _rs.default_audit_state()
        state.update({
            "status":        "running",
            "started_utc":   started,
            "heartbeat_utc": _rs.now_iso(),   # heartbeat keeps the lease fresh
            "progress":      progress,
        })
        repo.save_run_state(_rs.AUDIT_KEY, state)

    def _on_progress(p: Dict[str, Any]) -> None:
        # Called from the executor thread; the Firestore client is thread-safe.
        _write_running(p)

    _write_running({"current_city": "", "completed": 0, "total": total})

    try:
        from engine.pipeline import run_full_audit
        fixtures = DEMO_FIXTURES if demo else None
        loop     = asyncio.get_event_loop()
        result   = await loop.run_in_executor(
            None, lambda: run_full_audit(targets, repo, fixtures,
                                         progress_cb=_on_progress)
        )
        repo.save_run_state(_rs.AUDIT_KEY, {
            **_rs.default_audit_state(),
            "status":        "completed",
            "started_utc":   started,
            "finished_utc":  _rs.now_iso(),
            "heartbeat_utc": _rs.now_iso(),
            "progress":      {"current_city": "", "completed": total, "total": total},
            **result,
        })
    except Exception as exc:
        ref = str(uuid.uuid4())[:8]
        tb  = _tb.format_exc()
        print(f"[audit_task] ERROR [{ref}] {type(exc).__name__}: {exc}\n{tb}")
        repo.save_run_state(_rs.AUDIT_KEY, {
            **_rs.default_audit_state(),
            "status":         "error",
            "started_utc":    started,
            "finished_utc":   _rs.now_iso(),
            "heartbeat_utc":  _rs.now_iso(),
            "error":          f"Audit pipeline error. Reference ID: {ref}",
            "last_traceback": f"[{ref}] {type(exc).__name__}: {exc}\n{tb}",
        })


@router.post("/run", response_model=AuditRunResponse)
@limiter.limit("5/minute")
async def trigger_audit(
    request: Request,
    background_tasks: BackgroundTasks,
    demo: bool = False,
    city_filter: Optional[str] = None,
    cities: Optional[str] = None,   # comma-separated multi-select from the dashboard
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    # NOTE: the "already running" guard is enforced atomically below via
    # repo.claim_run_slot() once the target list is known — it is cross-instance
    # (a Firestore transaction), unlike the old per-process check that let two
    # Cloud Run instances start concurrent audits.
    principal = resolve_principal(user, repo)
    if not principal.can_trigger_audit():
        raise HTTPException(
            status_code=403,
            detail="Your role does not permit running audits. Contact your administrator.")

    # Requested cities: explicit multi-select > single city_filter > all-visible.
    requested = None
    if cities:
        requested = [c.strip() for c in cities.split(",") if c.strip()]
    elif city_filter:
        requested = [city_filter]
    # Intersect with what this principal may audit (fail-secure).
    allowed_cities = scope_requested_cities(requested, principal)

    if demo:
        targets = [
            {"url": k, "city": v["city"], "jurisdiction": "TX", "domain": k}
            for k, v in DEMO_FIXTURES.items()
        ]
    else:
        targets = repo.get_targets()
        if not principal.all_cities:
            # Hard tenant boundary: a scoped user can never audit outside scope.
            targets = [t for t in targets if t.get("city") in principal.cities]
        if allowed_cities:
            # Explicit selection (single re-audit or multi-select): scan exactly
            # these. Individual re-audit is the only path that re-scrapes a proxy
            # city on demand; proxy cost is incurred deliberately.
            sel = set(allowed_cities)
            targets = [t for t in targets if t.get("city") in sel]
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

    # Atomic, cross-instance claim of the single audit slot. Returns None if a
    # fresh run already holds it (409); a run whose heartbeat has gone stale for
    # AUDIT_LEASE_STALE_SECONDS is presumed dead and can be superseded.
    claimed = repo.claim_run_slot(
        _rs.AUDIT_KEY,
        now_utc=_rs.now_iso(),
        total=len(targets),
        stale_after_seconds=config.AUDIT_LEASE_STALE_SECONDS,
    )
    if claimed is None:
        raise HTTPException(status_code=409, detail="Audit already running")

    background_tasks.add_task(_run_audit_task, targets, demo, repo)
    try:
        repo.append_audit_log(
            event="audit_triggered", city_count=len(targets), failures=0,
            details={
                "actor":   user.get("email", "unknown"),
                "summary": (f"Scan started for {', '.join(allowed_cities)}"
                            if allowed_cities
                            else f"Full scan started ({len(targets)} cities)"),
                "scope":   ", ".join(allowed_cities) if allowed_cities else "all",
                "cities":  allowed_cities[0] if len(allowed_cities) == 1 else None,
                "demo":    demo,
            })
    except Exception as exc:
        print(f"[activity] WARN: could not log audit_triggered: {exc}")
    # Respond from the freshly-claimed state. status="started" mirrors the old
    # contract (the dashboard then polls GET /run for live progress).
    return AuditRunResponse(status="started", **{
        k: claimed.get(k) for k in AuditRunResponse.model_fields if k != "status"
    })


@router.get("/run", response_model=AuditRunResponse)
def get_audit_status(repo: GovernanceRepository = Depends(get_repository)):
    # Read the shared run state so any instance reports the same status/progress.
    state = {**_rs.default_audit_state(), **repo.get_run_state(_rs.AUDIT_KEY)}
    # Select only model fields — heartbeat_utc/last_traceback are internal.
    return AuditRunResponse(**{k: state.get(k) for k in AuditRunResponse.model_fields})


@router.get("/trace")
def get_audit_trace(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Admin-only: return the raw traceback from the last failed audit run."""
    if not is_admin(user["email"]):
        raise HTTPException(status_code=403, detail="Admin only")
    state = repo.get_run_state(_rs.AUDIT_KEY)
    return {
        "status":         state.get("status"),
        "error":          state.get("error"),
        "last_traceback": state.get("last_traceback"),
        "started_utc":    state.get("started_utc"),
        "finished_utc":   state.get("finished_utc"),
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
        # Store under a separate key so a Deep Scan error never clobbers the
        # live audit run-state document.
        try:
            repo.save_run_state("chrome_capture", {
                "last_traceback": f"[chrome_capture:{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}",
                "finished_utc":   _rs.now_iso(),
            })
        except Exception:
            pass
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
