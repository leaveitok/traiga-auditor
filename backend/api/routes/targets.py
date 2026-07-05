"""
targets.py -- Target Registry endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/targets", tags=["targets"])


class TargetCreate(BaseModel):
    city: str
    jurisdiction: str = "TX"
    domain: str
    url: str
    tags: List[str] = []
    cloudflare_protected: bool = False


@router.get("")
def list_targets(repo: GovernanceRepository = Depends(get_repository)):
    # TODO: enforce role check -- viewer or admin only (auth placeholder)
    return repo.get_targets()


@router.post("", status_code=201)
def create_target(
    body: TargetCreate,
    repo: GovernanceRepository = Depends(get_repository),
):
    # TODO: enforce admin-only write permission (auth placeholder)
    created = repo.add_target(
        city=body.city,
        jurisdiction=body.jurisdiction,
        domain=body.domain,
        url=body.url,
        tags=body.tags,
        cloudflare_protected=body.cloudflare_protected,
    )
    # Instant visibility: a target has no scorecard row until its first scan,
    # which made newly added cities invisible on the dashboard. Write a
    # not_assessed placeholder row now; the first scan overwrites it (upsert
    # keyed on city). Non-fatal if it fails — the target itself was created.
    try:
        repo.write_scorecard_rows([{
            "city":               body.city,
            "jurisdiction":       body.jurisdiction,
            "domain":             body.domain,
            "ai_assets_detected": [],
            "traiga_status":      "not_assessed",
            "open_violations":    [],
            "min_days_remaining": "",
            "compliance_score":   "",
            "band":               "",
            "last_scanned_utc":   "",
        }])
    except Exception as exc:
        print(f"[targets] WARN: placeholder scorecard row failed for "
              f"{body.city}: {type(exc).__name__}: {exc}")
    return created


@router.delete("/{target_id}", status_code=204)
def delete_target(
    target_id: str,
    repo: GovernanceRepository = Depends(get_repository),
):
    # TODO: enforce admin-only write permission (auth placeholder)
    ok = repo.deactivate_target(target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Target not found")
