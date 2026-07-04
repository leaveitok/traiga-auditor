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

# ── Shared mutable state accessed by the /audit/schedule endpoint ────────────
_scheduler_ref: Optional[AsyncIOScheduler] = None

_state: Dict[str, Any] = {
    "last_run_utc":    None,
    "last_result":     None,   # {"city_count": N, "observed_failures": N, "open_violations": N}
    "last_error":      None,
    "run_count":       0,
}


def get_scheduler_state() -> Dict[str, Any]:
    """Return a snapshot of scheduler + run history for the status endpoint."""
    next_run: Optional[str] = None
    running = bool(_scheduler_ref and _scheduler_ref.running)
    if running:
        job = _scheduler_ref.get_job("scheduled_audit")  # type: ignore[union-attr]
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    return {
        "scheduler_running":  running,
        "scan_cadence_hours": config.SCAN_CADENCE_HOURS,
        "next_run_utc":       next_run,
        **_state,
    }


async def _scheduled_scan_job() -> None:
    """
    Core job: fetch auto-scannable targets → run_full_audit → update state.

    Cloudflare-protected targets are excluded; they surface in the
    manual_scan_cities count returned by GET /api/audit/schedule.
    """
    global _state

    # Import here to avoid circular-import at module load time
    from core.dependencies import get_repository
    from engine.pipeline import run_full_audit

    repo    = get_repository()
    targets = [t for t in repo.get_targets() if not t.get("cloudflare_protected", False)]

    if not targets:
        print("[scheduler] No auto-scannable targets — all targets may be Cloudflare-protected.")
        _state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
        _state["last_result"]  = {"city_count": 0, "observed_failures": 0, "open_violations": 0}
        _state["run_count"]   += 1
        return

    print(f"[scheduler] Starting scheduled scan of {len(targets)} city/cities ...")
    ref = str(uuid.uuid4())[:8]
    try:
        result = run_full_audit(targets, repo)
        _state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
        _state["last_result"]  = result
        _state["last_error"]   = None
        _state["run_count"]   += 1
        print(
            f"[scheduler] Scan complete [{ref}] — "
            f"cities={result['city_count']} "
            f"failures={result['observed_failures']} "
            f"open_violations={result['open_violations']}"
        )
    except Exception as exc:
        _state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
        _state["last_error"]   = f"Scan error [{ref}]: {type(exc).__name__}"
        _state["run_count"]   += 1
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
