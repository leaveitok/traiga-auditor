"""
remediation.py -- Remediation artifact generation endpoints.

POST /api/remediation/policy?city=City+of+Lewisville
    Returns a TRAIGA-compliant AI Use Policy Word document (.docx)
    pre-populated with the city's detected AI vendor inventory and
    open violations at the time of request.
"""
from __future__ import annotations

import os
import tempfile
import uuid
import traceback as _tb
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/remediation", tags=["remediation"])


@router.get("/policy")
def generate_policy(
    city: str,
    repo: GovernanceRepository = Depends(get_repository),
):
    """
    Generate a vendor-specific AI Use Policy Word document for a city.

    Fetches the city's scorecard (for detected_assets) and open violations
    from the repository, then delegates to engine.remediation.policy_generator.

    Returns the .docx file as an attachment download.
    """
    try:
        # ── Fetch data ───────────────────────────────────────────────────────
        scorecard_rows = repo.get_scorecard()
        city_row = next(
            (r for r in scorecard_rows if r.get("city", "").lower() == city.lower()),
            None,
        )

        violations = repo.get_violations(city=city)

        # ── Resolve target metadata ──────────────────────────────────────────
        targets    = repo.get_targets()
        target_row = next(
            (t for t in targets if t.get("city", "").lower() == city.lower()),
            None,
        )
        jurisdiction = (target_row or {}).get("jurisdiction", "TX")
        domain       = (target_row or {}).get("domain", "")

        # ── Parse detected AI assets ─────────────────────────────────────────
        import json
        detected_assets: list = []
        if city_row:
            raw_assets = city_row.get("detected_assets") or city_row.get("ai_assets") or "[]"
            if isinstance(raw_assets, str):
                try:
                    detected_assets = json.loads(raw_assets)
                except (json.JSONDecodeError, ValueError):
                    detected_assets = []
            elif isinstance(raw_assets, list):
                detected_assets = raw_assets

        scan_date = (city_row or {}).get("last_scanned") or (city_row or {}).get("scan_timestamp")

        # ── Generate document ────────────────────────────────────────────────
        from engine.remediation.policy_generator import generate_ai_use_policy

        tmp_dir = tempfile.mkdtemp()
        safe    = city.replace(" ", "_").replace("/", "_")
        out     = os.path.join(tmp_dir, f"{safe}_AI_Use_Policy.docx")

        generate_ai_use_policy(
            city=city,
            jurisdiction=jurisdiction,
            domain=domain,
            detected_assets=detected_assets,
            violations=violations,
            output_path=out,
            scan_date=scan_date,
        )

        filename = f"{safe}_AI_Use_Policy.docx"
        return FileResponse(
            path=out,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as exc:
        ref = str(uuid.uuid4())[:8]
        print(f"[remediation] ERROR [{ref}] {type(exc).__name__}: {exc}\n{_tb.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Policy generation failed. Reference ID: {ref}",
        )
