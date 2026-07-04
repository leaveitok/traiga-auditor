"""
reports.py — Compliance report generation endpoint.

GET /api/reports/generate?city=City+of+Frisco
  Fetches live scorecard + violation data for the city, runs generate_report.py,
  and returns the DOCX as a file download.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback as _tb
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/generate")
def generate_report(
    city: str,
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Generate a TRAIGA compliance report DOCX for a single city and return it
    as a file download.  Data is pulled live from the repository.
    TODO: enforce role check — viewer or admin only (auth placeholder).
    TODO: scope to requesting user's assigned city for city-scoped roles.
    """
    # ── Fetch scorecard row ────────────────────────────────────────────────────
    rows = repo.get_scorecard()
    city_row = next((r for r in rows if r.get("city") == city), None)
    if not city_row:
        raise HTTPException(
            status_code=404,
            detail=f"No scorecard data found for '{city}'. Run an audit first."
        )

    # Parse ai_assets JSON column
    try:
        ai_assets = json.loads(city_row.get("ai_assets_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        ai_assets = []

    # ── Fetch violations for this city ─────────────────────────────────────────
    all_violations = repo.get_violations()
    city_violations = [
        v for v in all_violations
        if v.get("city") == city and v.get("status") != "cured"
    ]

    # Parse evidence_json on each violation
    for v in city_violations:
        try:
            v["evidence"] = json.loads(v.get("evidence_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            v["evidence"] = {}

    # ── Build the data payload generate_report.py expects ─────────────────────
    scorecard_data = {
        "city":                city_row.get("city", city),
        "jurisdiction":        city_row.get("jurisdiction", "TX"),
        "domain":              city_row.get("domain", ""),
        "traiga_status":       city_row.get("traiga_status", "not_assessed"),
        "compliance_score":    city_row.get("compliance_score", 100),
        "band":                city_row.get("band", "green"),
        "open_violations_count": city_row.get("open_violations_count", 0),
        "min_days_remaining":  city_row.get("min_days_remaining", None),
        "last_scanned_utc":    city_row.get("last_scanned_utc", ""),
        "ai_assets":           ai_assets,
    }

    # ── Run generate_report.py ─────────────────────────────────────────────────
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    report_script = os.path.join(backend_dir, "scripts", "generate_report.py")

    if not os.path.exists(report_script):
        raise HTTPException(
            status_code=500,
            detail="Report generator not available. Contact your administrator."
        )

    # Write data to a temp file and pass to the script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8") as f:
        json.dump({
            "scorecard": scorecard_data,
            "violations": city_violations,
        }, f)
        data_path = f.name

    out_dir = tempfile.mkdtemp()
    safe_city = city.replace(" ", "_").replace("/", "_")
    out_path = os.path.join(out_dir, f"{safe_city}_TRAIGA_Compliance_Report.docx")

    try:
        sys.path.insert(0, backend_dir)
        import importlib.util
        spec = importlib.util.spec_from_file_location("generate_report", report_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with open(data_path, encoding="utf-8") as f:
            payload = json.load(f)

        doc_path = mod.generate(
            city=payload["scorecard"]["city"],
            scorecard=payload["scorecard"],
            violations=payload["violations"],
            output_path=out_path,
            brand=None,
        )
        return FileResponse(
            path=str(doc_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=os.path.basename(str(doc_path)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        # Log full detail server-side only
        ref = str(uuid.uuid4())[:8]
        print(f"[reports] ERROR [{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed. Reference ID: {ref}",
        )
    finally:
        try:
            os.unlink(data_path)
        except OSError:
            pass
