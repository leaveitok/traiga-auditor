import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
    """Liveness + build/version info. Unauthenticated (used by the Settings page).
    GIT_SHA is injected at deploy time (deploy.yml) = the true, unique build id.

    Two different identifiers, deliberately, because they answer different questions:
      release  - human-facing "01.7". What you ask a pilot city to read off their
                 screen, and what you look up in RELEASES.md. Not unique on its own
                 if someone ships without stamping, which is why it is not the only id.
      version  - the deployed commit SHA. Unique and unambiguous, but useless to say
                 out loud on a support call.
    This endpoint is the AUTHORITATIVE answer to "what is actually running?" - it reads
    the live process, whereas VERSION/RELEASES.md only record what was pushed. If CI
    went red after a green push, those two disagree and THIS one is right."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "release": os.environ.get("APP_RELEASE", "dev"),    # human-facing 01.X
        "version": os.environ.get("GIT_SHA", "dev")[:12],   # deployed commit (short SHA)
        "environment": "production" if os.environ.get("REQUIRE_AUTH", "false").lower() == "true" else "dev",
        "storage": os.environ.get("GOVERNANCE_STORE", "sheets"),
    }
