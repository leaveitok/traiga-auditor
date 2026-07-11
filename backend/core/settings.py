"""
settings.py — runtime operational settings (admin-toggleable feature flags).

Backed by the repository's existing key-value store (run_state doc "app_settings"),
so there is NO schema/Protocol change. Env vars in config are the DEFAULTS; the
stored doc overrides them at runtime, so a platform admin can flip a flag from the
UI without a redeploy.

HARD RULE: only NON-SENSITIVE operational toggles live here. Secrets (proxy URL,
service-account file, ingest tokens, project IDs) stay in Secret Manager / env and
are NEVER exposed through this module or the settings API.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from core import config

_KEY = "app_settings"
_TTL = 20  # seconds — a flip takes effect within this window across instances
_CACHE: Dict[str, Any] = {"t": 0.0, "data": {}}

# Allowlist — the ONLY settable keys. Each is wired to real runtime behavior.
SETTABLE: Dict[str, Dict[str, Any]] = {
    "AGENDA_ENGINE_ENABLED": {
        "type": "bool", "group": "Agenda discovery", "label": "Agenda engine enabled",
        "help": "Scan council/EDC agendas for procured AI. Off by default.",
        "default": lambda: config.AGENDA_ENGINE_ENABLED},
    "AGENDA_LLM_PROVIDER": {
        "type": "enum", "group": "Agenda discovery", "label": "Extractor",
        "options": ["keyword", "vertex", "none"],
        "help": "keyword = free, no LLM (items surface as review candidates); "
                "vertex = Gemini on Vertex AI (cleaner vendor/product); none = disabled.",
        "default": lambda: config.AGENDA_LLM_PROVIDER},
    "AGENDA_LOOKBACK_MONTHS": {
        "type": "int", "group": "Agenda discovery", "label": "Default lookback (months)",
        "min": 1, "max": config.AGENDA_LOOKBACK_MONTHS_MAX,
        "help": "How far back a scan reaches when no explicit date range is given.",
        "default": lambda: config.AGENDA_LOOKBACK_MONTHS},
}


def _defaults() -> Dict[str, Any]:
    return {k: v["default"]() for k, v in SETTABLE.items()}


def _stored(repo: Any) -> Dict[str, Any]:
    now = time.time()
    if now - _CACHE["t"] < _TTL:
        return _CACHE["data"]
    try:
        data = repo.get_run_state(_KEY) or {}
    except Exception:
        data = {}
    _CACHE.update(t=now, data=data)
    return data


def _coerce(key: str, val: Any) -> Any:
    spec = SETTABLE[key]
    if spec["type"] == "bool":
        return val if isinstance(val, bool) else str(val).strip().lower() in ("true", "1", "yes", "on")
    if spec["type"] == "int":
        try:
            n = int(val)
        except (ValueError, TypeError):
            return spec["default"]()
        return max(spec.get("min", n), min(spec.get("max", n), n))
    if spec["type"] == "enum":
        s = str(val)
        return s if s in spec.get("options", []) else spec["default"]()
    return str(val)


def get_all(repo: Any) -> Dict[str, Any]:
    """Effective settings: stored values over env defaults, allowlisted keys only."""
    eff = _defaults()
    stored = _stored(repo)
    for k in SETTABLE:
        if k in stored:
            eff[k] = _coerce(k, stored[k])
    return eff


def get_value(repo: Any, key: str) -> Any:
    return get_all(repo).get(key)


def get_bool(repo: Any, key: str) -> bool:
    return bool(get_value(repo, key))


def public_schema() -> Dict[str, Any]:
    """Control metadata for the UI (no default lambdas)."""
    out: Dict[str, Any] = {}
    for k, v in SETTABLE.items():
        out[k] = {"type": v["type"], "group": v["group"], "label": v["label"],
                  "help": v.get("help", ""), "options": v.get("options"),
                  "min": v.get("min"), "max": v.get("max")}
    return out


def save(repo: Any, updates: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
    """
    Validate + persist ONLY allowlisted keys; audit-log the change. Returns the
    new effective settings. TODO: enforce platform_admin (route enforces).
    """
    stored = dict(_stored(repo))
    applied: Dict[str, Any] = {}
    for k, v in (updates or {}).items():
        if k not in SETTABLE:
            continue
        stored[k] = _coerce(k, v)
        applied[k] = stored[k]
    repo.save_run_state(_KEY, stored)
    _CACHE.update(t=0.0, data={})   # invalidate so the change is seen immediately
    try:
        repo.append_audit_log(
            event="settings_changed", city_count=0, failures=0,
            details={"actor": actor, "summary": f"Updated settings: {', '.join(applied) or '(none)'}",
                     "changes": applied})
    except Exception as exc:
        print(f"[settings] WARN: could not audit settings change: {exc}")
    return get_all(repo)
