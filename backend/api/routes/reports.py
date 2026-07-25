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

import os

from fastapi.responses import Response

from core.auth import get_current_user
from core.access import resolve_principal
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository
from engine import rule_loader
from core.reporting import bundle_orchestrator as bo

router = APIRouter(prefix="/reports", tags=["reports"])


def _release() -> str:
    return os.environ.get("APP_RELEASE", "dev")


def _require_city_scope(user, repo, city):
    """Read-but-sensitive: the caller must be allowed to see this city. Generating a
    bundle is not a mutation, but it exposes a city's full compliance posture, so it is
    scoped exactly like reading that city.
    TODO: attach verified user context for multi-tenant scoping (auth placeholder)."""
    principal = resolve_principal(user, repo)
    if not (principal.all_cities or principal.can_see_city(city)):
        raise HTTPException(status_code=403, detail="City out of scope.")
    return principal


@router.get("/presets")
def list_presets(
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Audience presets for the Reports section. Data-driven from SCHEMA_DEFINITION.json,
    so a new audience appears here with no code change."""
    # TODO: role gate if presets ever become tenant-specific (auth placeholder)
    return {"presets": bo.list_presets(rule_loader.load_schema())}


@router.get("/preview")
def preview_bundle(
    city: str,
    preset: str,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Return the render-agnostic BundleModel so the UI can show a live, on-brand HTML
    preview BEFORE generating a file. No document is produced here."""
    _require_city_scope(user, repo, city)
    try:
        model = bo.build_model(repo, city, preset, rule_loader.load_schema(), tool_release=_release())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown preset '{preset}'.")
    except LookupError:
        raise HTTPException(status_code=404, detail=f"No data for '{city}'. Run an audit first.")
    return model


@router.get("/bundle")
def generate_bundle(
    city: str,
    preset: str,
    fmt: str = "pdf",
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Generate ONE tailored document (pdf|docx) for a preset. On-demand; not persisted
    in Phase 1."""
    _require_city_scope(user, repo, city)
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status_code=400, detail="fmt must be pdf or docx.")
    try:
        model = bo.build_model(repo, city, preset, rule_loader.load_schema(), tool_release=_release())
        data = bo.render_single(model, fmt)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown preset '{preset}'.")
    except LookupError:
        raise HTTPException(status_code=404, detail=f"No data for '{city}'. Run an audit first.")
    try:
        repo.append_audit_log(event="report_bundle_generated", city_count=1, failures=0,
                              details={"actor": user.get("email", "unknown"), "city": city,
                                       "preset": preset, "fmt": fmt,
                                       "content_sha256": model["meta"]["content_sha256"],
                                       "summary": f"{model['meta']['preset_title']} ({fmt}) generated for {city}"})
    except Exception as exc:
        print(f"[reports] WARN: could not audit-log bundle: {exc}")
    fn = f"{model['meta']['doc_id']}.{fmt}"
    return Response(content=data, media_type=bo.media_type(fmt),
                    headers={"Content-Disposition": f'attachment; filename="{fn}"',
                             "X-Content-SHA256": model["meta"]["content_sha256"]})


@router.get("/package")
def generate_package(
    city: str,
    preset: str,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    """Generate the full auditor package as a zip: PDF + DOCX + attachments + manifest."""
    _require_city_scope(user, repo, city)
    schema = rule_loader.load_schema()
    presets = (schema.get("Report_Bundles", {}) or {}).get("presets", {})
    if preset not in presets:
        raise HTTPException(status_code=404, detail=f"Unknown preset '{preset}'.")
    if not presets[preset].get("package"):
        raise HTTPException(status_code=400,
                            detail=f"Preset '{preset}' is a single document, not a package.")
    try:
        data = bo.build_package(repo, city, preset, schema, tool_release=_release())
    except LookupError:
        raise HTTPException(status_code=404, detail=f"No data for '{city}'. Run an audit first.")
    try:
        repo.append_audit_log(event="report_package_generated", city_count=1, failures=0,
                              details={"actor": user.get("email", "unknown"), "city": city,
                                       "preset": preset,
                                       "summary": f"Evidence package generated for {city}"})
    except Exception as exc:
        print(f"[reports] WARN: could not audit-log package: {exc}")
    safe = city.replace(" ", "_").replace("/", "_")
    return Response(content=data, media_type=bo.media_type("zip"),
                    headers={"Content-Disposition": f'attachment; filename="{safe}_Evidence_Package.zip"'})


@router.get("/generate")
def generate_report(
    city: str,
    repo: GovernanceRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    """
    Generate a TRAIGA compliance report DOCX for a single city and return it
    as a file download.  Data is pulled live from the repository.
    TODO: enforce role check — viewer or admin only (auth placeholder).
    TODO: scope to requesting user's assigned city for city-scoped roles.
    """
    try:
        repo.append_audit_log(
            event="report_generated", city_count=1, failures=0,
            details={"actor": user.get("email", "unknown"),
                     "summary": f"Compliance report generated for {city}",
                     "city": city})
    except Exception as exc:
        print(f"[activity] WARN: could not log report_generated: {exc}")

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
