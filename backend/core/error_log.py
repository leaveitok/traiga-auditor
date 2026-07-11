"""
error_log.py — fail-safe operational error recorder.

The audit log answers "who did what" (governance actions). The error log
answers "what broke" (unhandled pipeline/scheduler/collector failures) so a
platform admin can triage without SSHing into Cloud Run logs.

HARD RULE (opposite of the usual fail-secure): recording an error must NEVER
crash the caller. A failure in the logging path is swallowed and printed —
the original exception the caller is handling always takes precedence.

    from core.error_log import record_error
    try:
        run_full_audit(...)
    except Exception as exc:
        record_error(repo, source="audit_pipeline",
                     message=f"{type(exc).__name__}: {exc}",
                     details={"ref": ref, "traceback": tb})
        raise  # or handle — recording never interferes
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Recognised severities (free-form is allowed, but the UI styles these).
LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"

# Keep individual field payloads bounded so a giant traceback can't bloat a
# single Firestore document / Sheet cell.
_MAX_MESSAGE = 500
_MAX_DETAIL_STR = 8000


def _truncate(value: str, limit: int) -> str:
    if value is None:
        return ""
    value = str(value)
    return value if len(value) <= limit else value[:limit] + "…[truncated]"


def record_error(
    repo: Any,
    *,
    source: str,
    message: str,
    level: str = LEVEL_ERROR,
    city: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Append one entry to the durable error log via the injected repository.

    Returns True if the write succeeded, False if it was swallowed. Never
    raises. `source` is the subsystem (e.g. "audit_pipeline", "scheduler",
    "agenda_llm"); `details` carries structured context (ref id, traceback).

    TODO: enforce system-level write only once auth context is threaded here.
    """
    try:
        safe_details: Dict[str, Any] = {}
        for k, v in (details or {}).items():
            safe_details[str(k)] = (
                _truncate(v, _MAX_DETAIL_STR) if isinstance(v, str) else v
            )
        repo.append_error_log(
            source=source or "unknown",
            message=_truncate(message, _MAX_MESSAGE),
            level=level or LEVEL_ERROR,
            city=city,
            details=safe_details,
        )
        return True
    except Exception as log_exc:  # noqa: BLE001 — logging must never crash caller
        print(f"[error_log] failed to record error from {source!r}: {log_exc}")
        return False
