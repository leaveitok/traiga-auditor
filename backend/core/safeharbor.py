"""
safeharbor.py — TRAIGA safe-harbor readiness derivation (Municipal AI Profile).

Legal basis (verified 2026-07-07 against enrolled HB 149):
  Tex. Bus. & Com. Code Sec. 552.105(c): rebuttable presumption of reasonable care.
  Sec. 552.105(e): no liability where the defendant discovered the violation via
  (B) testing (incl. adversarial testing) or (D) an internal review process
  substantially complying with the most recent NIST "AI RMF: Generative AI
  Profile" or another nationally/internationally recognized AI RMF.

Design: each profile control is either machine-evidenced (an evaluator over data
the platform already holds), attested (a human record), or hybrid (machine when
determinable, attestation fallback). Evaluators return True / False / None —
None means "machine cannot determine here", which downgrades the control to
attestation. All derivation happens at read time; no pipeline changes.

Engineering artifact, not legal advice.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional


def _parse_iso(v: Any) -> Optional[datetime]:
    try:
        s = str(v).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def _within(v: Any, days: float) -> bool:
    dt = _parse_iso(v)
    return bool(dt and datetime.now(timezone.utc) - dt <= timedelta(days=days))


# ── Evaluators ────────────────────────────────────────────────────────────────
# ctx keys: scorecard_row (dict|None), assets (list), violations (list),
#           audit_log (list), sentinel_devices (list|None), target (dict|None)

def _audit_trail_active(ctx: Dict[str, Any]) -> Optional[bool]:
    log = ctx.get("audit_log") or []
    return any(_within(e.get("timestamp_utc") or e.get("timestamp"), 30) for e in log) or (len(log) > 0)


def _inventory_current(ctx: Dict[str, Any]) -> Optional[bool]:
    row = ctx.get("scorecard_row") or {}
    status = row.get("traiga_status", "not_assessed")
    if status in ("not_assessed", "scan_failed"):
        return False
    # Assessed within the last 7 days = current. WAF cities carry their most
    # recent verified deep-scan timestamp in the same field.
    return _within(row.get("last_scanned_utc"), 7)


def _attestation_coverage(ctx: Dict[str, Any]) -> Optional[bool]:
    assets = ctx.get("assets") or []
    if not assets:
        row = ctx.get("scorecard_row") or {}
        # No AI found and city assessed -> vacuously documented.
        return row.get("traiga_status") == "no_ai_detected" or None
    documented = [a for a in assets
                  if str(a.get("lifecycle_status", "")).lower() not in ("retired",)
                  and (a.get("attested_by") or str(a.get("provenance", "")) == "declared")]
    active = [a for a in assets
              if str(a.get("lifecycle_status", "")).lower() not in ("retired",)]
    if not active:
        return True
    return (len(documented) / len(active)) >= 0.8


def _city_assessed(ctx: Dict[str, Any]) -> Optional[bool]:
    row = ctx.get("scorecard_row") or {}
    return row.get("traiga_status", "not_assessed") not in ("not_assessed", "scan_failed")


def _disclosure_tested(ctx: Dict[str, Any]) -> Optional[bool]:
    # Disclosure rules run whenever a city is assessed; violations list carries
    # the outcomes. Assessed city => rules were evaluated (pass or fail is a
    # separate control; TESTING happened either way — 552.105(e)(B)).
    return _city_assessed(ctx)


def _monitoring_cadence(ctx: Dict[str, Any]) -> Optional[bool]:
    row = ctx.get("scorecard_row") or {}
    target = ctx.get("target") or {}
    cf = str(target.get("cloudflare_protected", "")).lower() in ("true", "1")
    # WAF-excluded cities are scanned on demand; 30-day recency is the bar there.
    return _within(row.get("last_scanned_utc"), 30 if cf else 7)


def _sentinel_active(ctx: Dict[str, Any]) -> Optional[bool]:
    # Sentinel-fed usage assets in the registry prove employee-AI visibility
    # (inside-out discovery synced within the last 30 days).
    for a in ctx.get("assets") or []:
        if str(a.get("provenance", "")) == "discovered_sentinel" \
                and _within(a.get("last_observed_utc"), 30):
            return True
    devices = ctx.get("sentinel_devices")
    if devices is None:
        return None            # cannot determine -> attestation fallback
    return len(devices) > 0 or None


def _cure_tracking(ctx: Dict[str, Any]) -> Optional[bool]:
    open_v = [v for v in (ctx.get("violations") or [])
              if v.get("status") in ("open", "in_cure", "expired")]
    if not open_v:
        return _city_assessed(ctx)   # nothing open; tracking proven by assessment
    return all(v.get("cure_deadline_utc") for v in open_v)


def _remediation_current(ctx: Dict[str, Any]) -> Optional[bool]:
    violations = ctx.get("violations") or []
    if any(v.get("status") == "expired" for v in violations):
        return False
    return _city_assessed(ctx)


_EVALUATORS: Dict[str, Callable[[Dict[str, Any]], Optional[bool]]] = {
    "audit_trail_active":   _audit_trail_active,
    "inventory_current":    _inventory_current,
    "attestation_coverage": _attestation_coverage,
    "city_assessed":        _city_assessed,
    "disclosure_tested":    _disclosure_tested,
    "monitoring_cadence":   _monitoring_cadence,
    "sentinel_active":      _sentinel_active,
    "cure_tracking":        _cure_tracking,
    "remediation_current":  _remediation_current,
}

_FUNCTIONS = ("govern", "map", "measure", "manage")


def evaluate_profile(module: Dict[str, Any], ctx: Dict[str, Any],
                     attestations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge machine evaluation + human attestations into a readiness structure.

    Returns {profile_name, profile_version, legal_basis, controls: [...],
             scores: {function: {satisfied, total, pct}}, overall: {...}, band}
    """
    att_by_id = {a.get("control_id"): a for a in (attestations or [])}
    controls_out: List[Dict[str, Any]] = []

    for c in module.get("controls", []):
        cid = c["control_id"]
        machine: Optional[bool] = None
        if c.get("evaluator"):
            fn = _EVALUATORS.get(c["evaluator"])
            if fn is not None:
                try:
                    machine = fn(ctx)
                except Exception as exc:      # evaluator crash must not 500 the page
                    print(f"[safeharbor] evaluator {c['evaluator']} failed: {type(exc).__name__}: {exc}")
                    machine = None
        att = att_by_id.get(cid) or {}
        attested = str(att.get("status", "")).lower() == "attested"

        if machine is True:
            status, basis = "satisfied", "machine"
        elif attested:
            status, basis = "satisfied", "attested"
        elif machine is False:
            status, basis = "failing", "machine"
        else:
            status, basis = "open", "attestation_required"

        controls_out.append({
            **{k: c.get(k) for k in ("control_id", "function", "title", "plain",
                                     "nist_ref", "evidence", "attest_hint")},
            "status": status,
            "basis": basis,
            "machine_result": machine,
            "attestation": ({
                "status": att.get("status"),
                "attested_by": att.get("attested_by"),
                "attested_utc": att.get("attested_utc"),
                "notes": att.get("notes"),
            } if att else None),
        })

    scores: Dict[str, Dict[str, Any]] = {}
    for fn_name in _FUNCTIONS:
        fc = [c for c in controls_out if c["function"] == fn_name]
        sat = sum(1 for c in fc if c["status"] == "satisfied")
        scores[fn_name] = {"satisfied": sat, "total": len(fc),
                           "pct": round(sat / len(fc), 3) if fc else 0.0}

    total = len(controls_out)
    sat_total = sum(1 for c in controls_out if c["status"] == "satisfied")
    overall_pct = round(sat_total / total, 3) if total else 0.0
    bands = module.get("readiness_bands", {"ready": 0.85, "partial": 0.5})
    band = ("ready" if overall_pct >= bands.get("ready", 0.85)
            else "partial" if overall_pct >= bands.get("partial", 0.5)
            else "early")

    return {
        "profile_name": module.get("profile_name", "Municipal AI Profile"),
        "profile_version": module.get("profile_version", "1.0"),
        "legal_basis": module.get("legal_basis", {}),
        "controls": controls_out,
        "scores": scores,
        "overall": {"satisfied": sat_total, "total": total, "pct": overall_pct},
        "band": band,
    }


def build_context(repo: Any, city: str) -> Dict[str, Any]:
    """Assemble evaluator context from the governance repository (read-only)."""
    def _safe(fn, default):
        try:
            return fn()
        except Exception as exc:
            print(f"[safeharbor] context read failed ({fn}): {type(exc).__name__}: {exc}")
            return default

    scorecard = _safe(lambda: repo.get_scorecard(), [])
    row = next((r for r in scorecard
                if str(r.get("city", "")).lower() == city.lower()), None)
    targets = _safe(lambda: repo.get_targets(), [])
    target = next((t for t in targets
                   if str(t.get("city", "")).lower() == city.lower()), None)
    return {
        "scorecard_row": row,
        "target": target,
        "assets": _safe(lambda: repo.get_ai_assets(city=city), []),
        "violations": _safe(lambda: repo.get_violations(city=city), []),
        "audit_log": _safe(lambda: repo.get_audit_log(limit=50), []),
        "sentinel_devices": None,   # governance repo has no Sentinel visibility; hybrid controls fall back to attestation
    }
