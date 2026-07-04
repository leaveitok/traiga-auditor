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
SCAN_CADENCE_HOURS: int = 24

# Number of consecutive scans that must find NO violation before it is
# auto-cured.  Prevents a single headless-crawler false negative from
# wiping a legitimate open violation off the board.  Set to 2 so the
# violation must disappear on two back-to-back scans before auto-curing.
CURE_CONFIRM_SCANS: int = 2

MAX_PAGES_PER_SITE: int = 3
MAX_DEPTH: int = 1
CRAWL_DELAY_SECONDS: float = 1.0
REQUEST_TIMEOUT_SECONDS: int = 15
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
