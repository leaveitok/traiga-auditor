"""
sentinel.py — AI-GRC Sentinel (internal browser-DLP) endpoints.

Two trust domains, two auth mechanisms — never mixed:

  INGEST  (POST /sentinel/ingest)
      Caller: the browser extension's service worker on employee machines.
      Auth:   X-Sentinel-Token shared device token (SENTINEL_INGEST_TOKENS env).
              Fail-secure: no tokens configured -> 503, everything rejected.
      Data:   metadata-only packets validated against the extension's
              violation-packet schema. Pydantic extra='forbid' is the server-side
              equivalent of the schema's additionalProperties:false — a packet
              carrying prompt text, filenames, or hashes is REJECTED, not stripped,
              so a leaky client version fails loudly in staging.

  READ    (GET /sentinel/...)
      Caller: humans on the dashboard.
      Auth:   Firebase user, AGENCY-SCOPED. A platform admin sees all DLP data;
              an agency admin/viewer sees only their own cities' events/devices
              (via _scope_events on the principal's city grant). Rows without a
              city tag are platform-admin-only (fail-secure for employee data).
"""
from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.access import resolve_principal
from core.auth import get_current_user
from core.dependencies import get_repository, get_sentinel_repository, limiter
from core.repositories.sentinel_repository import SentinelRepository

router = APIRouter(prefix="/sentinel", tags=["sentinel"])

HEARTBEAT_INTERVAL_MINUTES = 15
SILENT_AFTER_MISSED = 2  # heartbeats missed before a device is flagged silent


# ── Ingest auth (device token, constant-time compare) ────────────────────────
def _ingest_tokens() -> List[str]:
    return [t.strip() for t in os.environ.get("SENTINEL_INGEST_TOKENS", "").split(",") if t.strip()]


def require_device_token(x_sentinel_token: Optional[str] = Header(default=None)) -> str:
    tokens = _ingest_tokens()
    if not tokens:
        # Fail-secure: unconfigured ingest accepts nothing (never fail-open).
        raise HTTPException(status_code=503, detail="Sentinel ingest not configured")
    if not x_sentinel_token or not any(hmac.compare_digest(x_sentinel_token, t) for t in tokens):
        raise HTTPException(status_code=401, detail="Invalid device token")
    return x_sentinel_token


# ── Read auth (agency-scoped) ─────────────────────────────────────────────────
def _scope_events(rows: List[Dict[str, Any]], principal) -> List[Dict[str, Any]]:
    """Filter Sentinel rows to the principal's cities. Platform admins see all;
    an agency admin/viewer sees only their granted cities; rows without a city
    tag are platform-admin-only (fail-secure for employee-monitoring data).

    This IS the Sentinel read wall — every read route resolves a Principal and
    passes its rows through here. There is no separate role gate: an agency user
    with no city grant simply sees nothing."""
    if principal.all_cities:
        return rows
    allowed = principal.cities
    return [r for r in rows if r.get("city") and r.get("city") in allowed]


# ── Packet models (mirror webextension/schema/violation-packet.schema.json) ──
class _Detection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str
    pattern_id: str
    match_count: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class _Browser(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str


class _App(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: str
    origin: str

    @field_validator("origin")
    @classmethod
    def origin_only(cls, v: str) -> str:
        # Origin ONLY — URL paths/queries can embed conversation content.
        if not v.startswith("https://") or any(c in v[8:] for c in "/?#"):
            raise ValueError("origin must be scheme+host only (no path/query/fragment)")
        return v


class _FileMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extension: str = Field(max_length=12)
    size_bytes: int
    scannable: bool


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    event_id: str = Field(min_length=8)
    timestamp_utc: str
    device_id: str
    user_id: str
    extension_version: str
    ruleset_version: str
    # Optional tenant tag: the MDM-managed extension config stamps the device's
    # city so DLP telemetry can be scoped to that municipality. Absent until the
    # extension is configured to send it -> such events are platform-admin-only
    # (fail-secure for employee-monitoring data).
    city: Optional[str] = None


class ViolationPacket(_Envelope):
    packet_type: Literal["violation"]
    browser: _Browser
    app: _App
    trigger: Literal["submit_click", "enter_key", "file", "file_drop", "file_input", "paste"]
    payload_class: Literal["text", "file"]
    file_meta: Optional[_FileMeta] = None
    detections: List[_Detection] = Field(min_length=1)
    action_taken: Literal["blocked", "warned", "allowed_override", "audited"]


class HeartbeatPacket(_Envelope):
    packet_type: Literal["heartbeat"]
    policies_loaded: int = Field(ge=0)
    last_scan_utc: Optional[str] = None
    status: Literal["ok", "ruleset_missing", "degraded"]


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/ingest", status_code=202)
@limiter.limit("120/minute")
def ingest(
    request: Request,
    packet: ViolationPacket | HeartbeatPacket,
    _token: str = Depends(require_device_token),
    repo: SentinelRepository = Depends(get_sentinel_repository),
):
    """Accept one metadata-only packet from a Sentinel extension."""
    if isinstance(packet, HeartbeatPacket):
        repo.store_heartbeat({
            "event_id": packet.event_id,
            "timestamp_utc": packet.timestamp_utc,
            "device_id": packet.device_id,
            "user_id": packet.user_id,
            "extension_version": packet.extension_version,
            "ruleset_version": packet.ruleset_version,
            "policies_loaded": packet.policies_loaded,
            "last_scan_utc": packet.last_scan_utc or "",
            "status": packet.status,
            "city": packet.city or "",
        })
    else:
        repo.store_event({
            "event_id": packet.event_id,
            "timestamp_utc": packet.timestamp_utc,
            "device_id": packet.device_id,
            "user_id": packet.user_id,
            "browser_name": packet.browser.name,
            "browser_version": packet.browser.version,
            "extension_version": packet.extension_version,
            "ruleset_version": packet.ruleset_version,
            "site_id": packet.app.site_id,
            "origin": packet.app.origin,
            "trigger": packet.trigger,
            "city": packet.city or "",
            "payload_class": packet.payload_class,
            "file_ext": packet.file_meta.extension if packet.file_meta else "",
            "file_size_bytes": packet.file_meta.size_bytes if packet.file_meta else "",
            "file_scannable": str(packet.file_meta.scannable) if packet.file_meta else "",
            "detections_json": json.dumps([d.model_dump() for d in packet.detections]),
            "action_taken": packet.action_taken,
        })
    return {"accepted": True, "event_id": packet.event_id}


@router.get("/events")
def list_events(
    policy_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 200,
    user: dict = Depends(get_current_user),
    repo: SentinelRepository = Depends(get_sentinel_repository),
    gov_repo=Depends(get_repository),
):
    principal = resolve_principal(user, gov_repo)
    rows = _scope_events(
        repo.get_events(policy_id=policy_id, user_id=user_id, limit=min(limit, 1000)),
        principal)
    for r in rows:
        try:
            r["detections"] = json.loads(r.get("detections_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["detections"] = []
        r.pop("detections_json", None)
    return rows


@router.get("/summary")
def summary(
    user: dict = Depends(get_current_user),
    repo: SentinelRepository = Depends(get_sentinel_repository),
    gov_repo=Depends(get_repository),
):
    principal = resolve_principal(user, gov_repo)
    events = _scope_events(repo.get_events(limit=1000), principal)
    by_policy: Dict[str, int] = {}
    by_site: Dict[str, int] = {}
    blocked = 0
    for e in events:
        try:
            dets = json.loads(e.get("detections_json", "[]")) if "detections_json" in e else e.get("detections", [])
        except (json.JSONDecodeError, TypeError):
            dets = []
        for d in dets:
            pid = d.get("policy_id", "unknown")
            by_policy[pid] = by_policy.get(pid, 0) + 1
        site = e.get("site_id", "unknown")
        by_site[site] = by_site.get(site, 0) + 1
        if e.get("action_taken") == "blocked":
            blocked += 1
    hb = _scope_events(_device_status(repo), principal)
    return {
        "total_events": len(events),
        "blocked": blocked,
        "by_policy": by_policy,
        "by_site": by_site,
        "devices_reporting": sum(1 for d in hb if not d["silent"]),
        "devices_silent": sum(1 for d in hb if d["silent"]),
    }


def _device_status(repo: SentinelRepository) -> List[Dict[str, Any]]:
    """Latest heartbeat per device + silent flag (tamper canary)."""
    latest: Dict[str, Dict[str, Any]] = {}
    for h in repo.get_heartbeats():
        d = h.get("device_id", "unknown")
        if d not in latest:  # get_heartbeats is newest-first
            latest[d] = h
    now = datetime.now(timezone.utc)
    out = []
    threshold_s = HEARTBEAT_INTERVAL_MINUTES * 60 * SILENT_AFTER_MISSED
    for d, h in latest.items():
        silent = True
        age_s = None
        try:
            ts = datetime.fromisoformat(str(h.get("timestamp_utc", "")).replace("Z", "+00:00"))
            age_s = (now - ts).total_seconds()
            silent = age_s > threshold_s
        except ValueError:
            pass
        out.append({
            "device_id": d,
            "user_id": h.get("user_id", ""),
            "city": h.get("city", ""),
            "last_heartbeat_utc": h.get("timestamp_utc", ""),
            "age_seconds": int(age_s) if age_s is not None else None,
            "extension_version": h.get("extension_version", ""),
            "ruleset_version": h.get("ruleset_version", ""),
            "status": h.get("status", ""),
            "silent": silent,
        })
    out.sort(key=lambda r: (not r["silent"], r["device_id"]))
    return out


@router.get("/devices")
def device_status(
    user: dict = Depends(get_current_user),
    repo: SentinelRepository = Depends(get_sentinel_repository),
    gov_repo=Depends(get_repository),
):
    principal = resolve_principal(user, gov_repo)
    return _scope_events(_device_status(repo), principal)
