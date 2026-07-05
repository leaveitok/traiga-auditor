"""
main.py — FastAPI application entrypoint for the AI Transparency Auditor v2.

Start with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Environment variables (see .env.example):
    GOOGLE_SERVICE_ACCOUNT_FILE   path to service-account JSON key
    SPREADSHEET_ID                Google Sheets spreadsheet ID
    CORS_ORIGINS                  comma-separated list of allowed origins
    SCAN_CADENCE_HOURS            hours between automated scans (default 24)

─── Storage migration ────────────────────────────────────────────────────────
To swap Google Sheets for Firestore (or any other backend), change ONE line in
core/dependencies.py — the concrete class returned by get_repository().
No route file, engine module, or service changes required.
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core import config
from core.dependencies import get_repository, limiter
from api.routes import health, targets, audit, scorecard, violations, logs, reports, auth_routes, remediation, sentinel


# ── Lifespan handler (replaces deprecated @app.on_event) ─────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: startup → yield → shutdown.

    Startup:
      1. Warm the singleton repository and verify Google Sheets schema
         (background thread — health endpoint available immediately).
      2. Build and start the APScheduler for automated periodic scans.

    Shutdown:
      1. Gracefully stop the scheduler (non-blocking, max 5 s wait).
    """
    from core.scheduler import build_scheduler

    def _init_schema():
        try:
            get_repository().ensure_schema()
            print("[startup] Storage schema verified OK.")
        except Exception as exc:
            print(f"[startup] Storage schema check failed (non-fatal): {exc}")

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _init_schema)   # warm connection in background; requests serialize via SheetsRepository lock

    scheduler = build_scheduler()
    scheduler.start()
    print(
        f"[startup] Scheduler started — "
        f"auto-scan every {config.SCAN_CADENCE_HOURS} h (Cloudflare-protected cities skipped)."
    )

    yield  # application is running

    scheduler.shutdown(wait=False)
    print("[shutdown] Scheduler stopped.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Transparency Auditor API",
    description=(
        "External observer for TRAIGA / HB 149 public-sector AI disclosure compliance. "
        "Crawls municipal websites, fingerprints AI assets, and tracks 60-day cure periods."
    ),
    version="2.3.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — SlowAPIMiddleware enforces default_limits on all routes.
# Audit endpoints declare stricter per-route limits via @limiter.limit().
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── Routes ────────────────────────────────────────────────────────────────────
# Route modules use Depends(get_repository) — no module-level injection needed.
for router in [health.router, targets.router, audit.router,
               scorecard.router, violations.router, logs.router,
               reports.router, auth_routes.router, remediation.router,
               sentinel.router]:
    app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.API_HOST, port=config.API_PORT, reload=True)
