"""
auth.py — Firebase ID token verification and role-based access control.

Usage in route handlers:
    from core.auth import get_current_user, is_admin

    @router.post("/run")
    async def trigger_audit(user=Depends(get_current_user), ...):
        if not is_admin(user["email"]):
            # enforce city scoping via user["city"]
            ...

When REQUIRE_AUTH=false (default for local dev), a missing Bearer token is
treated as a synthetic admin so existing dev workflows stay unbroken.
Set REQUIRE_AUTH=true in production.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import config

security = HTTPBearer(auto_error=False)

_firebase_initialized = False


def _ensure_firebase() -> None:
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(config.GOOGLE_SERVICE_ACCOUNT_FILE)
            firebase_admin.initialize_app(cred)
        _firebase_initialized = True
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="firebase-admin not installed. Run: pip install firebase-admin --break-system-packages",
        )


def is_admin(email: str) -> bool:
    """Return True if email is in the ADMIN_EMAILS config list."""
    return email.lower() in {e.lower() for e in config.ADMIN_EMAILS}


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """
    FastAPI dependency — verify Firebase ID token from Authorization: Bearer <token>.

    Dev mode (REQUIRE_AUTH=false):
        - No token → returns synthetic admin user, unblocking local dev.
        - Token present → still verified (tests the auth path during dev).

    Production (REQUIRE_AUTH=true):
        - No token → 401.
        - Invalid token → 401.
    """
    if creds is None:
        if not config.REQUIRE_AUTH:
            # Dev shortcut: unauthenticated requests run as the first admin
            admin_email = config.ADMIN_EMAILS[0] if config.ADMIN_EMAILS else "dev@local"
            return {"uid": "dev", "email": admin_email, "role": "admin", "city": None}
        raise HTTPException(status_code=401, detail="Authentication required")

    _ensure_firebase()
    try:
        from firebase_admin import auth as fb_auth

        decoded = fb_auth.verify_id_token(creds.credentials)
    except Exception as exc:
        # Log detail server-side; never expose Firebase internals to client
        print(f"[auth] Token verification failed: {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "uid":   decoded.get("uid"),
        "email": decoded.get("email", ""),
        "role":  None,   # populated by /api/auth/me after Users sheet lookup
        "city":  None,
    }
