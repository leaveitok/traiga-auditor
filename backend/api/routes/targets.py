"""
targets.py -- Target Registry endpoints.

Routes depend only on GovernanceRepository (Protocol) injected via Depends.
Storage implementation is configured once in core/dependencies.py.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository


def _log_activity(repo, event: str, details: dict) -> None:
    """System activity trail — never let logging break the action itself."""
    try:
        repo.append_audit_log(event=event, city_count=0, failures=0, details=details)
    except Exception as exc:
        print(f"[activity] WARN: could not log {event}: {type(exc).__name__}: {exc}")

router = APIRouter(prefix="/targets", tags=["targets"])


class TargetCreate(BaseModel):
    city: str
    jurisdiction: str = "TX"
    domain: str
    url: str
    tags: List[str] = []
    cloudflare_protected: bool = False
    population: int = 0


@router.get("")
def list_targets(repo: GovernanceRepository = Depends(get_repository)):
    # TODO: enforce role check -- viewer or admin only (auth placeholder)
    return repo.get_targets()


@router.post("", status_code=201)
def create_target(
    body: TargetCreate,
    repo: GovernanceRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    # TODO: enforce admin-only write permission (auth placeholder)
    created = repo.add_target(
        city=body.city,
        jurisdiction=body.jurisdiction,
        domain=body.domain,
        url=body.url,
        tags=body.tags,
        cloudflare_protected=body.cloudflare_protected,
        population=body.population,
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
    _log_activity(repo, "target_added", {
        "actor": user.get("email", "unknown"),
        "summary": f"Added {body.city} ({body.domain})",
        "city": body.city,
        "cloudflare_protected": body.cloudflare_protected,
    })
    return created


class BulkTargetRow(BaseModel):
    city: str
    domain: str
    url: str = ""
    jurisdiction: str = "TX"
    tags: List[str] = []
    cloudflare_protected: bool = False
    population: int = 0


class BulkImportRequest(BaseModel):
    rows: List[BulkTargetRow]


_MAX_BULK_ROWS = 2000  # TAGITM full list is ~1,200; hard cap guards abuse


def _norm_domain(raw: str) -> str:
    """Normalize a domain for dedupe: strip scheme, path, port, www., case."""
    d = (raw or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].split(":")[0]
    return re.sub(r"^www\.", "", d)


@router.post("/bulk", status_code=201)
def bulk_import_targets(
    body: BulkImportRequest,
    repo: GovernanceRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    """
    Bulk-import audit targets (platform_admin ONLY).

    Agencies own their cities one at a time; only the platform operator has a
    legitimate reason to load a membership list (e.g. TAGITM ~1,200 cities).
    Imported targets are created as not_assessed and are NOT scanned
    automatically — scanning stays a deliberate action for proxy-cost control.

    Per-row failures never abort the batch: each row is validated and deduped
    independently and reported back in `skipped` with a reason.
    """
    principal = resolve_principal(user, repo)
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403,
                            detail="Bulk import is restricted to platform administrators")
    if not body.rows:
        raise HTTPException(status_code=400, detail="No rows submitted")
    if len(body.rows) > _MAX_BULK_ROWS:
        raise HTTPException(status_code=400,
                            detail=f"Too many rows ({len(body.rows)}); max {_MAX_BULK_ROWS} per import")

    existing = repo.get_targets()
    seen_cities  = {str(t.get("city", "")).strip().lower() for t in existing}
    seen_domains = {_norm_domain(str(t.get("domain", ""))) for t in existing}

    added: List[str] = []
    skipped: List[Dict[str, Any]] = []
    placeholder_rows: List[Dict[str, Any]] = []

    for i, row in enumerate(body.rows):
        line = i + 1
        city   = row.city.strip()
        domain = _norm_domain(row.domain)
        if not city or not domain or "." not in domain:
            skipped.append({"row": line, "city": city or "(blank)",
                            "reason": "missing or invalid city/domain"})
            continue
        if city.lower() in seen_cities:
            skipped.append({"row": line, "city": city, "reason": "duplicate city"})
            continue
        if domain in seen_domains:
            skipped.append({"row": line, "city": city,
                            "reason": f"duplicate domain ({domain})"})
            continue

        url = row.url.strip() or f"https://{domain}"
        try:
            repo.add_target(
                city=city,
                jurisdiction=row.jurisdiction.strip() or "TX",
                domain=domain,
                url=url,
                tags=row.tags,
                cloudflare_protected=row.cloudflare_protected,
                population=row.population,
            )
        except Exception as exc:
            skipped.append({"row": line, "city": city,
                            "reason": f"storage error: {type(exc).__name__}"})
            continue

        seen_cities.add(city.lower())
        seen_domains.add(domain)
        added.append(city)
        placeholder_rows.append({
            "city":               city,
            "jurisdiction":       row.jurisdiction.strip() or "TX",
            "domain":             domain,
            "ai_assets_detected": [],
            "traiga_status":      "not_assessed",
            "open_violations":    [],
            "min_days_remaining": "",
            "compliance_score":   "",
            "band":               "",
            "last_scanned_utc":   "",
        })

    # Instant dashboard visibility (same pattern as single create): imported
    # cities appear as not_assessed rows until their first scan. Non-fatal.
    if placeholder_rows:
        try:
            repo.write_scorecard_rows(placeholder_rows)
        except Exception as exc:
            print(f"[targets] WARN: bulk placeholder scorecard rows failed: "
                  f"{type(exc).__name__}: {exc}")

    _log_activity(repo, "targets_bulk_imported", {
        "actor": user.get("email", "unknown"),
        "summary": f"Bulk import: {len(added)} added, {len(skipped)} skipped "
                   f"of {len(body.rows)} submitted",
        "added_count": len(added),
        "skipped_count": len(skipped),
    })
    return {
        "added": len(added),
        "added_cities": added,
        "skipped": skipped,
        "total_submitted": len(body.rows),
    }


class TargetUpdate(BaseModel):
    """Partial update of an existing target. Omitted fields are unchanged.
    Every applied change is written to the audit log (target_updated)."""
    cloudflare_protected: Optional[bool] = None
    tags: Optional[List[str]] = None
    url: Optional[str] = None
    city: Optional[str] = None
    jurisdiction: Optional[str] = None
    domain: Optional[str] = None
    population: Optional[int] = None


@router.patch("/{target_id}")
def update_target(
    target_id: str,
    body: TargetUpdate,
    repo: GovernanceRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    """
    Edit scan settings on an existing target (platform_admin ONLY).

    Primary use: flag a city cloudflare_protected=true after a WAF-blocked
    scan, so the nightly scheduler excludes it from bulk runs and its
    Deep Scan result is not overwritten by the next automated failure.
    """
    principal = resolve_principal(user, repo)
    if not principal.is_platform_admin:
        raise HTTPException(status_code=403,
                            detail="Target settings are restricted to platform administrators")
    fields: Dict[str, Any] = {}
    if body.cloudflare_protected is not None:
        fields["cloudflare_protected"] = body.cloudflare_protected
    if body.tags is not None:
        fields["tags"] = body.tags
    if body.url is not None:
        fields["url"] = body.url
    if body.city is not None:
        fields["city"] = body.city
    if body.jurisdiction is not None:
        fields["jurisdiction"] = body.jurisdiction
    if body.domain is not None:
        fields["domain"] = body.domain
    if body.population is not None:
        fields["population"] = body.population
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    ok = repo.update_target(target_id, fields)
    if not ok:
        raise HTTPException(status_code=404, detail="Target not found")
    _log_activity(repo, "target_updated", {
        "actor": user.get("email", "unknown"),
        "summary": f"Updated target {target_id}: {', '.join(fields)}",
        "target_id": target_id,
        "fields": {k: str(v) for k, v in fields.items()},
    })
    return {"id": target_id, "updated": sorted(fields)}


@router.delete("/{target_id}", status_code=204)
def delete_target(
    target_id: str,
    repo: GovernanceRepository = Depends(get_repository),
    user: dict = Depends(get_current_user),
):
    # TODO: enforce admin-only write permission (auth placeholder)
    ok = repo.deactivate_target(target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Target not found")
    _log_activity(repo, "target_deactivated", {
        "actor": user.get("email", "unknown"),
        "summary": f"Deactivated target {target_id}",
        "target_id": target_id,
    })
