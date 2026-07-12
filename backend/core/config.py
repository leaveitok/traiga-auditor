"""
config.py — central configuration for the FastAPI backend.
All values are read from environment variables (see .env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Google Sheets ────────────────────────────────────────────────────────────
# Path to the downloaded service-account JSON key file.
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"
)
# The Spreadsheet ID from the Google Sheets URL:
#   https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
SPREADSHEET_ID: str = os.environ.get("SPREADSHEET_ID", "")

# Sheet tab names (create these tabs in your Google Spreadsheet).
SHEET_TARGETS    = "Targets"
SHEET_SCORECARD  = "Scorecard"
SHEET_VIOLATIONS = "Violations"
SHEET_AUDIT_LOG  = "AuditLog"
SHEET_ERROR_LOG  = "ErrorLog"
SHEET_USERS      = "Users"

# Admin emails (comma-separated) — these users can audit all cities
ADMIN_EMAILS: list = [e.strip() for e in os.environ.get("ADMIN_EMAILS", "leaveitok@gmail.com").split(",") if e.strip()]

# Set to true in production to require Firebase auth on audit endpoints
REQUIRE_AUTH: bool = os.environ.get("REQUIRE_AUTH", "false").lower() == "true"

# ── FastAPI ───────────────────────────────────────────────────────────────────
API_HOST: str = os.environ.get("API_HOST", "0.0.0.0")
API_PORT: int = int(os.environ.get("API_PORT", "8000"))
CORS_ORIGINS: list[str] = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

# ── Audit engine ─────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_FILE = PROJECT_DIR / "SCHEMA_DEFINITION.json"
CURE_PERIOD_DAYS: int = 60
SCAN_CADENCE_HOURS: int = 24   # legacy in-process interval; superseded by the daily-hour schedule below

# Automated daily scan (driven by Cloud Scheduler hitting /api/audit/scheduled-run).
# These are DEFAULTS; both are admin-toggleable at runtime via the Settings page.
SCAN_SCHEDULE_ENABLED: bool = os.environ.get("SCAN_SCHEDULE_ENABLED", "true").lower() == "true"
SCAN_SCHEDULE_HOUR: int = int(os.environ.get("SCAN_SCHEDULE_HOUR", "7"))   # UTC hour (0-23) to run the daily scan
# Shared token Cloud Scheduler sends (X-Scheduler-Token) to authorize the trigger.
# Secret; set via Secret Manager/env, NEVER exposed in the Settings API. Empty = trigger disabled (fail-secure).
SCHEDULER_TOKEN: str = os.environ.get("SCHEDULER_TOKEN", "").strip()

# Durable audit-run lease (cross-instance run state). A running scan refreshes
# its heartbeat after every city; if the heartbeat goes stale for longer than
# this, the holder's instance is presumed dead and a new run may steal the
# slot. Set generously so a slow WAF/proxy city is never mistaken for a crash;
# override via env for tuning without a code change.
AUDIT_LEASE_STALE_SECONDS: int = int(os.environ.get("AUDIT_LEASE_STALE_SECONDS", "900"))

# Number of consecutive scans that must find NO violation before it is
# auto-cured.  Prevents a single headless-crawler false negative from
# wiping a legitimate open violation off the board.  Set to 2 so the
# violation must disappear on two back-to-back scans before auto-curing.
CURE_CONFIRM_SCANS: int = 2

MAX_PAGES_PER_SITE: int = 3
MAX_DEPTH: int = 1
CRAWL_DELAY_SECONDS: float = 1.0
REQUEST_TIMEOUT_SECONDS: int = 15
# Proxy RENDER-tier requests run a real browser server-side (JS + cookie WAF
# challenge) and take far longer than a static fetch. ScraperAPI render can
# need up to ~70s, so use a separate, generous timeout for those requests only.
RENDER_TIMEOUT_SECONDS: int = int(os.environ.get("RENDER_TIMEOUT_SECONDS", "75"))
USER_AGENT: str = (
    "LewisvilleAITransparencyAuditor/2.0 (+external-observer; respects robots.txt)"
)

# ── Residential proxy (WAF bypass) ───────────────────────────────────────────
# Municipal sites behind Cloudflare/WAF serve bot-challenge pages to Google
# datacenter IPs (confirmed: cityoflewisville.com returns a 302-byte challenge
# to Cloud Run). Routing the crawler through a residential/ISP proxy presents a
# residential origin IP so the real page loads.
#
# Supply the full proxy URL via Secret Manager / env — never hardcode it:
#   SCAN_PROXY_URL=http://user:pass@proxy.provider.com:port
# Leave empty to crawl directly (local dev, or cities that don't block).
# SCAN_PROXY_ONLY_FLAGGED=true routes ONLY targets flagged cloudflare_protected
# through the proxy, to conserve paid proxy bandwidth.
SCAN_PROXY_URL: str = os.environ.get("SCAN_PROXY_URL", "").strip()
SCAN_PROXY_ONLY_FLAGGED: bool = os.environ.get("SCAN_PROXY_ONLY_FLAGGED", "false").lower() == "true"

# ── Council-agenda discovery engine (separate engine; isolated execution) ─────
# Flag-gated (off by default) so the LLM/PDF workload never runs against the core
# nightly compliance scan until deliberately enabled. See docs/AGENDA_ENGINE_DESIGN.md.
AGENDA_ENGINE_ENABLED: bool = os.environ.get("AGENDA_ENGINE_ENABLED", "false").lower() == "true"
# How far back an initial backfill scans agendas (cost control); incremental runs
# use the per-city last-scan date. Hard cap prevents an accidental years-deep scan.
AGENDA_LOOKBACK_MONTHS: int = int(os.environ.get("AGENDA_LOOKBACK_MONTHS", "12"))
AGENDA_LOOKBACK_MONTHS_MAX: int = int(os.environ.get("AGENDA_LOOKBACK_MONTHS_MAX", "36"))
# Extractor provider (single swap point): "keyword" (no LLM, zero-dep default —
# uses the item title so the AI-keyword screen still fires), "vertex" (Gemini on
# Vertex AI, reuses the GCP service account, enterprise no-train), or "none".
AGENDA_LLM_PROVIDER: str = os.environ.get("AGENDA_LLM_PROVIDER", "keyword").strip().lower()
AGENDA_LLM_MODEL: str = os.environ.get("AGENDA_LLM_MODEL", "gemini-2.5-flash-lite").strip()
AGENDA_LLM_LOCATION: str = os.environ.get("AGENDA_LLM_LOCATION", "us-central1").strip()
# Demand-driven proxy (NOT coupled to the website's cloudflare_protected flag —
# the agenda portal is usually a different third-party host). Sibling of SCAN_PROXY_*.
AGENDA_PROXY_URL: str = os.environ.get("AGENDA_PROXY_URL", os.environ.get("SCAN_PROXY_URL", "")).strip()

# ── Storage backend selection (Firestore migration, Phase 2) ─────────────────
# "sheets" (legacy) or "firestore". Defaults to sheets so ROLLBACK IS A CONFIG
# CHANGE: unset/flip the env var and redeploy — no cod