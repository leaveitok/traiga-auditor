"""
scorecard.py — roll up findings into the executive Compliance Scorecard.

Produces both a machine-readable JSON and a lightweight HTML view. Scoring
weights and bands come from SCHEMA_DEFINITION.json (scorecard_schema), so the
executive model is governed-as-code, not hard-coded here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from . import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _band(score: int, bands: Dict[str, List[int]]) -> str:
    for name, (lo, hi) in bands.items():
        if lo <= score <= hi:
            return name
    return "red"


def build_city_row(city: str, jurisdiction: str, domain: str,
                   assets: List[Dict[str, Any]],
                   open_violations: List[Dict[str, Any]],
                   scorecard_cfg: Dict[str, Any],
                   crawl_ok: bool = True,
                   used_proxy: bool = False) -> Dict[str, Any]:
    weights = scorecard_cfg["severity_weights"]
    in_cure_mult = scorecard_cfg.get("in_cure_weight_multiplier", 0.5)
    expired_mult = scorecard_cfg.get("expired_weight_multiplier", 1.0)

    score = scorecard_cfg.get("score_start", 100)
    days = [v["days_remaining"] for v in open_violations if v.get("cure_period_status")]
    # Earliest real cure deadline among open violations — lets the UI render the
    # countdown LIVE (deadline - now) instead of the stored days_remaining snapshot.
    _deadlines = [v.get("cure_deadline_utc") for v in open_violations if v.get("cure_deadline_utc")]
    min_cure_deadline_utc = min(_deadlines) if _deadlines else None   # ISO strings sort chronologically
    for v in open_violations:
        base = weights.get(v.get("severity", "medium"), 12)
        mult = in_cure_mult if v.get("status") == "in_cure" else (
            expired_mult if v.get("status") == "expired" else 1.0)
        score -= base * mult
    score = max(0, int(round(score)))

    # Status resolution. When there are no open violations we must distinguish
    # several very different situations that were previously all "not_assessed":
    #   - branded asset present     -> compliant (AI found, disclosures OK)
    #   - only candidate asset(s)   -> review_needed (an unrecognized chatbot was
    #                                  seen but not confirmed — NEVER shows clean)
    #   - crawl OK, no assets       -> no_ai_detected (assessed; site has no AI)
    #   - crawl failed / 0 captures -> scan_failed (WAF/error; could not assess)
    branded_assets   = [a for a in assets
                        if a.get("verification_status") != "candidate_review"]
    candidate_assets = [a for a in assets
                        if a.get("verification_status") == "candidate_review"]
    if not open_violations:
        if branded_assets:
            status = "compliant"
        elif candidate_assets:
            status = "review_needed"
        elif crawl_ok:
            status = "no_ai_detected"
        else:
            status = "scan_failed"
    elif any(v.get("status") == "expired" for v in open_violations):
        status = "expired"
    elif all(v.get("status") == "in_cure" for v in open_violations):
        status = "in_cure"
    else:
        status = "non_compliant"

    return {
        "city": city,
        "jurisdiction": jurisdiction,
        "domain": domain,
        "ai_assets_detected": assets,
        "traiga_status": status,
        "sb149_status": status,  # legacy alias key
        "open_violations": open_violations,
        "min_days_remaining": min(days) if days else None,
        "min_cure_deadline_utc": min_cure_deadline_utc,
        "compliance_score": score,
        "band": _band(score, scorecard_cfg["bands"]),
        "last_scanned_utc": _now_iso(),
        "last_scan_via_proxy": bool(used_proxy),
    }


def build_scorecard(rows: List[Dict[str, Any]],
                    scorecard_cfg: Dict[str, Any]) -> Dict[str, Any]:
    sort_cfg = scorecard_cfg.get("sort", {"by": "min_days_remaining", "order": "asc"})

    def sort_key(r):
        val = r.get(sort_cfg["by"])
        return (val is None, val if val is not None else 9999)

    rows_sorted = sorted(rows, key=sort_key,
                         reverse=(sort_cfg.get("order") == "desc"))
    return {
        "generated_utc": _now_iso(),
        "legal_basis": "Texas HB 149 / TRAIGA (Tex. Bus. & Com. Code Ch. 552)",
        "scan_cadence_hours": scorecard_cfg.get("scan_cadence_hours", 24),
        "cure_period_days": scorecard_cfg.get("cure_period_days", 60),
        "city_count": len(rows_sorted),
        "rows": rows_sorted,
    }


def render_html(scorecard: Dict[str, Any]) -> str:
    band_color = {"green": "#1a7f37", "amber": "#b58105", "red": "#b42318"}
    head = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>AI Transparency Compliance Scorecard</title>"
        "<style>body{font-family:system-ui,Arial,sans-serif;margin:24px;}"
        "table{border-collapse:collapse;width:100%;}"
        "th,td{border:1px solid #ddd;padding:8px;text-align:left;font-size:14px;}"
        "th{background:#f4f4f5;}.pill{padding:2px 8px;border-radius:10px;color:#fff;font-size:12px;}"
        "small{color:#666;}</style></head><body>"
    )
    title = (
        f"<h1>AI Transparency Compliance Scorecard</h1>"
        f"<p><small>Legal basis: {scorecard['legal_basis']} &middot; "
        f"Generated {scorecard['generated_utc']} &middot; "
        f"{scorecard['city_count']} cities &middot; "
        f"Cure period {scorecard['cure_period_days']} days / "
        f"scan every {scorecard['scan_cadence_hours']}h</small></p>"
    )
    rows_html = [
        "<table><tr><th>City</th><th>Domain</th><th>AI assets</th>"
        "<th>TRAIGA status</th><th>Score</th><th>Min days remaining</th></tr>"
    ]
    for r in scorecard["rows"]:
        color = band_color.get(r.get("band", "red"), "#b42318")
        assets = ", ".join(a.get("display_name", a.get("vendor_id", "?"))
                           for a in r["ai_assets_detected"]) or "—"
        mdr = r["min_days_remaining"] if r["min_days_remaining"] is not None else "—"
        rows_html.append(
            f"<tr><td>{r['city']}</td><td>{r['domain']}</td><td>{assets}</td>"
            f"<td>{r['traiga_status']}</td>"
            f"<td><span class='pill' style='background:{color}'>{r['compliance_score']}</span></td>"
            f"<td>{mdr}</td></tr>"
        )
    rows_html.append("</table>")
    foot = ("<p><small>Findings are candidate compliance signals from externally "
            "observable evidence and require human/legal review. Not legal advice.</small></p>"
            "</body></html>")
    return head + title + "".join(rows_html) + foot


def write_scorecard(scorecard: Dict[str, Any]) -> Dict[str, Path]:
    json_path = Path(config.local_path(config.SCORECARD_JSON))
    html_path = Path(config.local_path(config.SCORECARD_HTML))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(scorecard, fh, indent=2)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_html(scorecard))
    return {"json": json_path, "html": html_path}
