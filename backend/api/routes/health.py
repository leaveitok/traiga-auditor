import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
    """Liveness + build/version info. Unauthenticated (used by the Settings page).
    GIT_SHA is injected at deploy time (deploy.yml) = the true, unique build id."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": os.environ.get("GIT_SHA", "dev")[:12],   # deployed commit (short SHA)
        "environment": "production" if os.environ.get("REQUIRE_AUTH", "false").lower() == "true" else "dev",
        "storage": os.environ.get("GOVERNANCE_STORE", "sheets"),
    }
