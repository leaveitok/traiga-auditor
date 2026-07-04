"""
Shim: re-export core.config so engine modules can do `from . import config`
without modification.
"""
from core.config import (  # noqa: F401
    SCHEMA_FILE as _schema_file,
    CURE_PERIOD_DAYS,
    SCAN_CADENCE_HOURS,
    MAX_PAGES_PER_SITE,
    MAX_DEPTH,
    CRAWL_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)
from pathlib import Path

# engine/config surface expected by the existing modules
GDRIVE_ROOT = ""
PROJECT_DIR = Path(__file__).resolve().parent.parent
LOCAL_MIRROR_ROOT = PROJECT_DIR

SCHEMA_FILE     = "SCHEMA_DEFINITION.json"
TARGET_REGISTRY = "data/target_registry.json"
SCORECARD_JSON  = "dashboard/compliance_scorecard.json"
SCORECARD_HTML  = "dashboard/compliance_scorecard.html"
AUDIT_LOG_DIR   = "audit_logs"
CURE_STATE_FILE = "state/cure_state.json"


def local_path(relative: str) -> Path:
    return LOCAL_MIRROR_ROOT / relative


def drive_path(relative: str) -> str:
    return relative
