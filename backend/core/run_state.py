"""
run_state.py — pure helpers for durable, cross-instance run state.

WHY THIS EXISTS
───────────────
Cloud Run serves the API from N interchangeable instances. Historically the
"is an audit running / how far along is it" status lived in a module-global
dict inside a single process (api/routes/audit.py `_audit_state`, and
core/scheduler.py `_state`). That state is invisible to the other instances:

  * a GET /audit/run status poll routed to a different instance reports a
    stale "idle" while a scan is actually running elsewhere;
  * the "audit already running" guard is per-process, so two instances can
    launch concurrent full audits (double proxy spend, double writes);
  * a freshly-started instance boots with the default dict → the intermittent
    500-on-fresh-instance symptom.

`--session-affinity` only papers over this and is the prime suspect behind the
~5-minute dashboard-auth symptom (affinity pins a client to a Playwright-busy
instance). The durable fix is to keep run state in the shared datastore, read
and written ONLY through the GovernanceRepository — no route or scheduler ever
touches a storage provider directly.

This module holds the STORAGE-AGNOSTIC decision logic so it can be unit-tested
once, independently of Firestore/Sheets/Mock. Each repository implements the
thin persistence wrapper (a Firestore transaction, a Sheets/in-memory
read-modify-write) around these helpers.

CONCURRENCY MODEL (the "run slot" lease)
────────────────────────────────────────
Exactly one full audit may hold the slot at a time. A holder marks the slot
`status="running"` and refreshes `heartbeat_utc` after every city. A would-be
claimant may take the slot only if it is not currently running OR the current
holder's heartbeat is older than `stale_after_seconds` (the holder is presumed
dead — e.g. its instance crashed mid-scan). Without the staleness escape a
crashed run would wedge the slot forever, which is worse than the original bug.

The manual trigger and the nightly scheduler share ONE slot key ("audit") so a
scheduled scan can never collide with a manual one, and N instances can never
double-fire the nightly run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Shared slot/state keys (one document per key in the datastore).
AUDIT_KEY = "audit"          # the single full-audit run slot + live progress
SCHEDULER_KEY = "scheduler"  # durable scheduler run-history (last run, counts)


def now_iso() -> str:
    """UTC now as an ISO-8601 string (the wire format used everywhere here)."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO-8601 timestamp, tolerating None / '' / trailing 'Z' and
    naive strings. Returns a timezone-aware datetime (UTC) or None. Never
    raises — a bad/absent timestamp is treated as "unknown", which callers
    read as "lease is stale" (fail toward letting a new run proceed).
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def default_audit_state() -> Dict[str, Any]:
    """The idle template returned when no audit run-state has been written."""
    return {
        "status":            "idle",
        "started_utc":       None,
        "finished_utc":      None,
        "heartbeat_utc":     None,
        "city_count":        0,
        "observed_failures": 0,
        "open_violations":   0,
        "error":             None,
        "progress":          None,
    }


def running_state(now_utc: str, total: int) -> Dict[str, Any]:
    """
    Fresh 'running' state stamped at claim time. `total` is the number of
    cities in this run so the progress bar has a denominator immediately.
    """
    state = default_audit_state()
    state.update({
        "status":        "running",
        "started_utc":   now_utc,
        "finished_utc":  None,
        "heartbeat_utc": now_utc,
        "error":         None,
        "progress":      {"current_city": "", "completed": 0, "total": int(total)},
    })
    return state


def is_lease_stale(state: Dict[str, Any], now_utc: str,
                   stale_after_seconds: int) -> bool:
    """
    True if the running holder's heartbeat is older than stale_after_seconds
    (or unparseable/missing). Only meaningful when status == 'running'.
    """
    hb = parse_iso(state.get("heartbeat_utc")) or parse_iso(state.get("started_utc"))
    now = parse_iso(now_utc)
    if hb is None or now is None:
        return True
    return (now - hb).total_seconds() > float(stale_after_seconds)


def slot_available(state: Optional[Dict[str, Any]], now_utc: str,
                   stale_after_seconds: int) -> bool:
    """
    Decide whether the run slot may be claimed.

    Available when there is no state, the holder is not running, or the holder
    IS running but its lease has gone stale (presumed-dead instance). This is
    the single source of truth for the cross-instance 409 guard; every
    repository's claim implementation calls it inside its atomic section.
    """
    if not state:
        return True
    if str(state.get("status")) != "running":
        return True
    return is_lease_stale(state, now_utc, stale_after_seconds)
