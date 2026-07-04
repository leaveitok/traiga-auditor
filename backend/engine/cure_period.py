"""
cure_period.py — the 60-day Cure Period clock with a 24-hour refresh cadence.

Key invariant: the scan cadence (24h) NEVER changes the statutory 60-day clock.
The 60 days are anchored to first_observed_utc. The daily scan only:
  - opens a record the first time a violation is seen,
  - refreshes days_remaining,
  - marks a record 'cured' when the violation no longer reproduces
    on CURE_CONFIRM_SCANS consecutive scans (guards against single-scan
    false negatives from dynamic widgets that Playwright may miss),
  - marks a record 'expired' when days_remaining hits 0 and it still fails.

State persists to JSON so the countdown survives restarts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import config


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def make_violation_id(city: str, asset_id: str, rule_id: str) -> str:
    raw = f"{city}|{asset_id}|{rule_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def load_state(path: Path | None = None) -> Dict[str, Any]:
    state_path = path or config.local_path(config.CURE_STATE_FILE)
    if Path(state_path).exists():
        with open(state_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {"violations": {}}


def save_state(state: Dict[str, Any], path: Path | None = None) -> None:
    state_path = Path(path or config.local_path(config.CURE_STATE_FILE))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def _days_remaining(first_observed: datetime, now: datetime) -> int:
    elapsed = (now - first_observed).days
    return max(0, config.CURE_PERIOD_DAYS - elapsed)


def reconcile(
    state: Dict[str, Any],
    observed: List[Dict[str, Any]],
    crawled_cities: set | None = None,
    now: datetime | None = None,
) -> Dict[str, Any]:
    """Reconcile this scan's observed failures against persisted cure records.

    `observed` items must contain: city, domain, asset_id, vendor_id, rule_id,
    citation, severity, evidence.

    `crawled_cities`: set of city names that the crawler successfully retrieved
    content for in this scan.  A violation is only marked 'cured' when its city
    is in `crawled_cities` AND the violation was not re-observed.  This prevents
    three classes of false-cure:
      - City-scoped re-audits wiping violations for other cities
      - A WAF-blocked crawl (zero pages) clearing all of a city's violations
      - Missing vendor fingerprints making a real violation disappear

    Auto-cure requires CURE_CONFIRM_SCANS consecutive clean scans (default 2).
    This means a dynamic widget that Playwright misses on one pass will NOT
    wipe the violation — it must be absent on two back-to-back runs before the
    system concludes it has been remediated.  When a violation is observed again
    after clean scans, the counter resets to zero.

    Returns the updated state dict (violations for non-crawled cities are left
    untouched).
    """
    now = now or _now()
    violations: Dict[str, Any] = state.setdefault("violations", {})
    observed_ids = set()

    # 1) Open new / refresh existing.
    for obs in observed:
        vid = make_violation_id(obs["city"], obs["asset_id"], obs["rule_id"])
        observed_ids.add(vid)
        rec = violations.get(vid)
        if rec is None:
            first = now
            deadline = first + timedelta(days=config.CURE_PERIOD_DAYS)
            rec = {
                "violation_id": vid,
                "city": obs["city"],
                "domain": obs.get("domain", ""),
                "asset_id": obs["asset_id"],
                "vendor_id": obs.get("vendor_id", ""),
                "rule_id": obs["rule_id"],
                "citation": obs.get("citation", ""),
                "severity": obs.get("severity", "medium"),
                "first_observed_utc": _iso(first),
                "cure_deadline_utc": _iso(deadline),
                "evidence": obs.get("evidence", {}),
                "needs_human_review": True,
            }
            violations[vid] = rec

        first_dt = datetime.fromisoformat(rec["first_observed_utc"])
        rec["last_observed_utc"] = _iso(now)
        rec["days_remaining"] = _days_remaining(first_dt, now)
        rec["cure_period_status"] = rec["days_remaining"] > 0
        rec["status"] = "in_cure" if rec["days_remaining"] > 0 else "expired"
        # Violation re-observed — reset the consecutive-clean counter
        rec["consecutive_clean_scans"] = 0

    # 2) Records not observed this scan -> candidate cures.
    # ONLY mark cured when we have positive evidence the city was scanned and
    # the violation no longer reproduces.  Violations for cities outside
    # `crawled_cities` are left in their current state (in_cure / expired).
    #
    # ANTI-FALSE-NEGATIVE GUARD: require CURE_CONFIRM_SCANS consecutive clean
    # scans before marking cured.  A single missed detection (e.g. Playwright
    # not triggering a scroll-gated widget on one pass) will NOT auto-cure the
    # violation — the counter just increments.  Only after the widget has been
    # absent on CURE_CONFIRM_SCANS back-to-back runs do we conclude it is gone.
    for vid, rec in violations.items():
        if vid in observed_ids:
            continue
        if rec.get("status") in ("cured",):
            continue
        # Guard: only consider cure if we actually crawled this city in this run
        if crawled_cities is not None and rec.get("city") not in crawled_cities:
            continue

        clean = rec.get("consecutive_clean_scans", 0) + 1
        rec["consecutive_clean_scans"] = clean

        if clean >= config.CURE_CONFIRM_SCANS:
            rec["status"] = "cured"
            rec["cure_period_status"] = False
            rec["days_remaining"] = 0
            rec.setdefault("cured_utc", _iso(now))
        # else: leave status unchanged (in_cure or expired); violation stays open
        # until the next scan also finds it absent

    state["last_scan_utc"] = _iso(now)
    return state


def open_violations(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [v for v in state.get("violations", {}).values()
            if v.get("status") in ("open", "in_cure", "expired")]
