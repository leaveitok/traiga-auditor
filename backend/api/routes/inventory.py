"""
inventory.py — AI Use-Case Inventory endpoints (see docs/INVENTORY_SPEC.md).

The system-of-record for every AI system an agency runs: discovered
automatically by the scan pipeline, confirmed (attested) by a human.

RBAC (fail-secure):
  read   — any authenticated principal; rows filtered to visible cities.
  write  — platform_admin, or agency_admin whose scope contains the city.
Machine fields are never patchable through the API — scans own them.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.access import Principal, filter_rows, resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository
from core.governance_service import GovernanceRepository

router = APIRouter(prefix="/inventory", tags=["inventory"])

# Fields a human may write via declare/patch. Everything else is machine-owned.
_HUMAN_FIELDS = {
    "display_name", "asset_types_json", "owner_email", "owner_name",
    "attestation_note", "department", "purpose", "data_categories_json",
    "lifecycle_status",
}
_VALID_LIFECYCLE = {"discovered", "attested", "retired"}
_REVIEW_CADENCE_DAYS = 365


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _can_write(principal: Principal, city: str) -> bool:
    """platform_admin anywhere; agency_admin inside their city scope; else no."""
    if principal.is_platform_admin:
        return True
    return principal.is_agency_admin and principal.can_see_city(city)


# ── Read-time enrichment (never stored, so never stale) ──────────────────────

_OBLIGATIONS: Optional[List[Dict[str, str]]] = None


def _obligations() -> List[Dict[str, str]]:
    """Applicable external-transparency rules from the governance schema."""
    global _OBLIGATIONS
    if _OBLIGATIONS is None:
        try:
            from engine.rule_loader import load_schema
            rules = (load_schema().get("Compliance_Ruleset", {})
                     .get("External_Transparency_Module", {}).get("rules", []))
            _OBLIGATIONS = [{
                "rule_id":  r.get("rule_id", ""),
                "title":    r.get("title", ""),
                "citation": r.get("citation", ""),
                "severity": r.get("severity", ""),
            } for r in rules]
        except Exception:
            _OBLIGATIONS = []
    return _OBLIGATIONS


def _parse_json(value: Any, default: Any) -> Any:
    try:
        parsed = json.loads(value) if isinstance(value, str) and value else value
        return parsed if parsed is not None else default
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _enrich(asset: Dict[str, Any],
            open_by_city_vendor: Dict[tuple, int]) -> Dict[str, Any]:
    a = dict(asset)
    a["asset_types"]    = _parse_json(a.pop("asset_types_json", "[]"), [])
    a["data_categories"] = _parse_json(a.pop("data_categories_json", "[]"), [])
    a["evidence"]       = _parse_json(a.pop("evidence_json", "{}"), {})

    open_count = open_by_city_vendor.get(
        (a.get("city", ""), a.get("vendor_id", "")), 0)
    a["open_violation_count"] = open_count
    if a.get("provenance") == "discovered_scan":
        a["disclosure_status"] = "non_compliant" if open_count else "compliant"
    else:
        a["disclosure_status"] = "not_assessed"   # declared assets: scans can't see them
    a["obligations"] = _obligations()
    return a


def _open_violation_index(repo: GovernanceRepository) -> Dict[tuple, int]:
    idx: Dict[tuple, int] = {}
    try:
        for v in repo.get_violations():
            if str(v.get("status", "")).lower() in ("cured",):
                continue
            key = (v.get("city", ""), v.get("vendor_id", ""))
            idx[key] = idx.get(key, 0) + 1
    except Exception:
        pass
    return idx


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def list_inventory(
    city: Optional[str] = None,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    rows = filter_rows(repo.get_ai_assets(city=city), principal)
    open_idx = _open_violation_index(repo)
    return [_enrich(r, open_idx) for r in rows]


class DeclareAsset(BaseModel):
    city:            str
    display_name:    str
    asset_types:     List[str] = []
    department:      Optional[str] = None
    purpose:         Optional[str] = None
    data_categories: List[str] = []
    owner_email:     Optional[str] = None
    owner_name:      Optional[str] = None
    attestation_note: Optional[str] = None


@router.post("")
def declare_asset(
    body: DeclareAsset,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    principal = resolve_principal(user, repo)
    if not _can_write(principal, body.city):
        raise HTTPException(
            status_code=403,
            detail="Your role does not permit declaring assets for this city.")

    now = _now()
    key = (f"{body.city.strip().lower().replace(' ', '-')}"
           f"::decl-{str(uuid.uuid4())[:8]}")
    record = {
        "asset_key":           key,
        "city":                body.city,
        "vendor_id":           "",
        "display_name":        body.display_name,
        "asset_types_json":    json.dumps(body.asset_types),
        "provenance":          "declared",
        "lifecycle_status":    "attested",   # self-declared = attested by declarer
        "presence":            "active",
        "first_observed_utc":  now,
        "last_observed_utc":   now,
        "owner_email":         body.owner_email or "",
        "owner_name":          body.owner_name or "",
        "attested_by":         user.get("email", ""),
        "attested_utc":        now,
        "attestation_note":    body.attestation_note or "",
        "department":          body.department or "",
        "purpose":             body.purpose or "",
        "data_categories_json": json.dumps(body.data_categories),
        "next_review_utc":     (datetime.now(timezone.utc)
                                + timedelta(days=_REVIEW_CADENCE_DAYS)).isoformat(),
    }
    saved = repo.upsert_ai_asset(record)
    try:
        repo.append_audit_log(
            event="asset_declared", city_count=1, failures=0,
            details={"actor": user.get("email", ""), "city": body.city,
                     "summary": f"AI asset declared: {body.display_name} "
                                f"({body.city})"})
    except Exception as exc:
        print(f"[inventory] WARN: audit log failed: {exc}")
    return _enrich(saved, _open_violation_index(repo))


class PatchAsset(BaseModel):
    display_name:     Optional[str] = None
    asset_types:      Optional[List[str]] = None
    owner_email:      Optional[str] = None
    owner_name:       Optional[str] = None
    department:       Optional[str] = None
    purpose:          Optional[str] = None
    data_categories:  Optional[List[str]] = None
    attestation_note: Optional[str] = None
    lifecycle_status: Optional[str] = None   # attest / retire


@router.patch("/{asset_key}")
def patch_asset(
    asset_key: str,
    body: PatchAsset,
    user: dict = Depends(get_current_user),
    repo: GovernanceRepository = Depends(get_repository),
):
    existing = next((r for r in repo.get_ai_assets()
                     if r.get("asset_key") == asset_key), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Asset not found")

    principal = resolve_principal(user, repo)
    city = existing.get("city", "")
    if not principal.can_see_city(city):
        raise HTTPException(status_code=404, detail="Asset not found")
    if not _can_write(principal, city):
        raise HTTPException(
            status_code=403,
            detail="Your role does not permit modifying this asset.")

    if body.lifecycle_status and body.lifecycle_status not in _VALID_LIFECYCLE:
        raise HTTPException(status_code=400,
                            detail=f"Invalid lifecycle_status: {body.lifecycle_status}")

    patch: Dict[str, Any] = {"asset_key": asset_key}
    if body.display_name is not None:     patch["display_name"] = body.display_name
    if body.asset_types is not None:      patch["asset_types_json"] = json.dumps(body.asset_types)
    if body.owner_email is not None:      patch["owner_email"] = body.owner_email
    if body.owner_name is not None:       patch["owner_name"] = body.owner_name
    if body.department is not None:       patch["department"] = body.department
    if body.purpose is not None:          patch["purpose"] = body.purpose
    if body.data_categories is not None:  patch["data_categories_json"] = json.dumps(body.data_categories)
    if body.attestation_note is not None: patch["attestation_note"] = body.attestation_note

    event = None
    if body.lifecycle_status and body.lifecycle_status != existing.get("lifecycle_status"):
        patch["lifecycle_status"] = body.lifecycle_status
        if body.lifecycle_status == "attested":
            patch["attested_by"]     = user.get("email", "")
            patch["attested_utc"]    = _now()
            patch["next_review_utc"] = (datetime.now(timezone.utc)
                                        + timedelta(days=_REVIEW_CADENCE_DAYS)).isoformat()
            event = "asset_attested"
        elif body.lifecycle_status == "retired":
            event = "asset_retired"

    saved = repo.upsert_ai_asset(patch)
    if event:
        try:
            repo.append_audit_log(
                event=event, city_count=1, failures=0,
                details={"actor": user.get("email", ""), "city": city,
                         "summary": f"AI asset {event.split('_')[1]}: "
                                    f"{saved.get('display_name', asset_key)} ({city})"})
        except Exception as exc:
            print(f"[inventory] WARN: audit log failed: {exc}")
    return _enrich(saved, _open_violation_index(repo))
