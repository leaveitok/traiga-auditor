"""
scheduler.py — APScheduler integration for automated periodic scanning.

The scheduler runs a full audit on every auto-scannable target
(cloudflare_protected=False) at the cadence set by config.SCAN_CADENCE_HOURS.
Cloudflare-protected targets are skipped and remain flagged for manual
Deep Scan via the Chrome MCP flow.

Exports:
  build_scheduler() -> AsyncIOScheduler   — creates, configures, returns the scheduler.
  get_scheduler_state() -> dict           — live snapshot for GET /api/audit/schedule.
"""
from __future__ import annotations

import traceback as _tb
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core import config
from core import run_state as _rs

# ── Scheduler object reference (a live, instance-local APScheduler) ──────────
# The scheduler runs on each instance; scheduler_running / next_run_utc are
# legitimately instance-local facts. The RUN HISTORY (last run, result, count),
# however, is durable and shared across instances via the repository under
# _rs.SCHEDULER_KEY — see get_scheduler_state() / _scheduled_scan_job().
_scheduler_ref: Optional[AsyncIOScheduler] = None


def _default_scheduler_history() -> Dict[str, Any]:
    """Idle template for the durable scheduler run-history document."""
    return {
        "last_run_utc": None,
        "last_result":  None,   # {"city_count": N, "observed_failures": N, "open_violations": N}
        "last_error":   None,
        "run_count":    0,
    }


def _running_audit_state(started: str, total: int) -> Dict[str, Any]:
    """A 'running' audit-slot document a scheduled scan writes as it heartbeats."""
    state = _rs.default_audit_state()
    state.update({
        "status":        "running",
        "started_utc":   started,
        "heartbeat_utc": _rs.now_iso(),
        "progress":      {"current_city": "", "completed": 0, "total": total},
    })
    return state


def _terminal_audit_state(started: str, status: str, total: int,
                          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Completed/error audit-slot document — releases the slot (status != running)."""
    state = _rs.default_audit_state()
    state.update({
        "status":        status,
        "started_utc":   started,
        "finished_utc":  _rs.now_iso(),
        "heartbeat_utc": _rs.now_iso(),
        "progress":      {"current_city": "", "completed": total, "total": total},
    })
    if extra:
        state.update(extra)
    return state


def get_scheduler_state() -> Dict[str, Any]:
    """Return a snapshot of scheduler + durable run history for the status endpoint."""
    next_run: Optional[str] = None
    running = bool(_scheduler_ref and _scheduler_ref.running)
    if running:
        job = _scheduler_ref.get_job("scheduled_audit")  # type: ignore[union-attr]
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    # Durable, cross-instance run history (falls back to the idle template).
    try:
        from core.dependencies import get_repository
        history = {**_default_scheduler_history(),
                   **(get_repository().get_run_state(_rs.SCHEDULER_KEY) or {})}
    except Exception as exc:
        print(f"[scheduler] WARN: could not read durable history: {exc}")
        history = _default_scheduler_history()

    return {
        "scheduler_running":  running,
        "scan_cadence_hours": config.SCAN_CADENCE_HOURS,
        "next_run_utc":       next_run,
        **history,
    }


def _record_scheduler_run(repo: Any, result: Optional[Dict[str, Any]],
                          error: Optional[str]) -> None:
    """Read-modify-write the durable scheduler history (run_count is monotonic).
    Safe without cross-instance atomicity because the shared audit slot claim
    serializes scheduled runs — only one instance is ever inside this path."""
    hist = {**_default_scheduler_history(),
            **(repo.get_run_state(_rs.SCHEDULER_KEY) or {})}
    hist["last_run_utc"] = _rs.now_iso()
    hist["last_result"]  = result
    hist["last_error"]   = error
    hist["run_count"]    = int(hist.get("run_count", 0) or 0) + 1
    repo.save_run_state(_rs.SCHEDULER_KEY, hist)


async def _scheduled_scan_job() -> None:
    """
    Core job: claim the shared audit slot → fetch auto-scannable targets →
    run_full_audit → record durable state. The claim guarantees a scheduled
    scan never collides with a manual Run Audit and that N instances never
    double-fire the nightly run (the previous per-process scheduler would fire
    once per live instance).

    Cloudflare-protected targets are excluded; they surface in the
    manual_scan_cities count returned by GET /api/audit/schedule.
    """
    # Import here to avoid circular-import at module load time
    from core.dependencies import get_repository
    from engine.pipeline import run_full_audit

    repo = get_repository()

    # Cross-instance guard: only one full audit at a time, across all instances
    # and across both the manual and scheduled trigger paths.
    started = _rs.now_iso()
    claimed = repo.claim_run_slot(
        _rs.AUDIT_KEY, now_utc=started, total=0,
        stale_after_seconds=config.AUDIT_LEASE_STALE_SECONDS,
    )
    if claimed is None:
        print("[scheduler] Audit slot already held (manual run or another "
              "instance) — skipping this scheduled tick.")
        return

    ref = str(uuid.uuid4())[:8]
    try:
        targets = [t for t in repo.get_targets()
                   if not t.get("cloudflare_protected", False)]

        if not targets:
            print("[scheduler] No auto-scannable targets — all targets may be Cloudflare-protected.")
            empty = {"city_count": 0, "observed_failures": 0, "open_violations": 0}
            _record_scheduler_run(repo, result=empty, error=None)
            repo.save_run_state(_rs.AUDIT_KEY,
                                _terminal_audit_state(started, "completed", 0))
            return

        total = len(targets)

        def _hb(p: Dict[str, Any]) -> None:
            # Heartbeat the shared audit slot so its lease stays fresh and the
            # dashboard reflects an in-progress scheduled scan too.
            st = _running_audit_state(started, total)
            st["progress"] = p
            repo.save_run_state(_rs.AUDIT_KEY, st)

        repo.save_run_state(_rs.AUDIT_KEY, _running_audit_state(started, total))
        print(f"[scheduler] Starting scheduled scan of {total} city/cities ...")

        result = run_full_audit(targets, repo, progress_cb=_hb)
        _record_scheduler_run(repo, result=result, error=None)
        repo.save_run_state(
            _rs.AUDIT_KEY,
            _terminal_audit_state(started, "completed", total, extra=result),
        )
        print(
            f"[scheduler] Scan complete [{ref}] — "
            f"cities={result['city_count']} "
            f"failures={result['observed_failures']} "
            f"open_violations={result['open_violations']}"
        )
    except Exception as exc:
        _record_scheduler_run(repo, result=None,
                              error=f"Scan error [{ref}]: {type(exc).__name__}")
        try:
            repo.save_run_state(_rs.AUDIT_KEY, _terminal_audit_state(
                started, "error", 0,
                extra={"error": f"Scan error [{ref}]",
                       "last_traceback": f"[{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}"}))
        except Exception:
            pass
        print(f"[scheduler] ERROR [{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}")


def build_scheduler() -> AsyncIOScheduler:
    """
    Build and return a configured AsyncIOScheduler.

    The caller (main.py lifespan handler) is responsible for calling
    scheduler.start() and scheduler.shutdown().

    The scheduler is NOT started here — separating build from start makes
    it straightforward to replace with a test scheduler in unit tests.
    """
    global _scheduler_ref

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _scheduled_scan_job,
        trigger=IntervalTrigger(hours=config.SCAN_CADENCE_HOURS),
        id="scheduled_audit",
        name="Automated TRAIGA Compliance Scan",
        replace_existing=True,
        misfire_grace_time=3600,   # allow up to 1 h late start if server was down
    )
    _scheduler_ref = scheduler
    return scheduler
