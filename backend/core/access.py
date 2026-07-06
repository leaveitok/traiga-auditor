"""
access.py — multi-tenant RBAC: roles, principal resolution, city scoping,
and delegated-administration bounds.

This is the SINGLE SOURCE OF TRUTH for "who can see/do what". Routes must not
re-implement scoping; they call resolve_principal() then visible_cities() /
can_manage_user() here. Fail-secure throughout: unknown role -> viewer with an
empty city set (sees nothing) rather than everything.

Tenancy model
─────────────
  platform_admin  — you (bootstrapped from ADMIN_EMAILS). All cities, all
                    agencies, all users. Can never be locked out.
  agency_admin    — manages users WITHIN their own agency and grants only
                    cities their agency holds. Full read/write on those cities.
  viewer          — read-only on the specific cities granted to them (a subset
                    of their agency's grant).

Cities are the unit of authorization. An agency is granted a set of cities;
a user belongs to one agency; a viewer is granted a subset of that agency's
cities; an agency_admin implicitly holds all of the agency's cities.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from core.auth import is_admin

ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_AGENCY_ADMIN   = "agency_admin"
ROLE_VIEWER         = "viewer"
VALID_ROLES = {ROLE_PLATFORM_ADMIN, ROLE_AGENCY_ADMIN, ROLE_VIEWER}

# Legacy role values (pre-multi-tenant) mapped forward on read.
_LEGACY_ROLE_MAP = {
    "admin":    ROLE_PLATFORM_ADMIN,
    "city":     ROLE_VIEWER,
    "security": ROLE_VIEWER,   # Sentinel access now flows from city scope
}


def _norm_role(role: Optional[str]) -> str:
    r = (role or "").strip().lower()
    r = _LEGACY_ROLE_MAP.get(r, r)
    return r if r in VALID_ROLES else ROLE_VIEWER


def _load_cities(raw: Any) -> Set[str]:
    """Parse a user's cities field (JSON list, or legacy single 'city')."""
    if not raw:
        return set()
    if isinstance(raw, (list, set)):
        return {str(c) for c in raw if c}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return {str(c) for c in parsed if c}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {str(raw)}  # legacy single city string


class Principal:
    """Resolved identity + authorization scope for the current request."""

    def __init__(self, email: str, role: str, agency_id: Optional[str],
                 cities: Optional[Set[str]], all_cities: bool):
        self.email      = email
        self.role       = role
        self.agency_id  = agency_id
        self._cities    = cities or set()
        self.all_cities = all_cities   # True => platform admin, unrestricted

    @property
    def is_platform_admin(self) -> bool:
        return self.role == ROLE_PLATFORM_ADMIN

    @property
    def is_agency_admin(self) -> bool:
        return self.role == ROLE_AGENCY_ADMIN

    @property
    def cities(self) -> Set[str]:
        return set(self._cities)

    def can_see_city(self, city: str) -> bool:
        return self.all_cities or city in self._cities

    def can_trigger_audit(self) -> bool:
        return self.role in (ROLE_PLATFORM_ADMIN, ROLE_AGENCY_ADMIN)


def resolve_principal(user: Dict[str, Any], repo: Any) -> Principal:
    """Turn a verified token identity into a fully-scoped Principal.

    `user` is what get_current_user() returns ({email, uid, ...}); the role,
    agency, and city grants come from the Users store (and the agency's grant).
    """
    email = (user or {}).get("email", "") or ""

    # Platform-admin bootstrap — always unrestricted, never store-dependent.
    if is_admin(email):
        return Principal(email, ROLE_PLATFORM_ADMIN, None, None, all_cities=True)

    row = {}
    try:
        row = repo.get_user(email) or {}
    except Exception as exc:
        print(f"[access] get_user failed for {email}: {type(exc).__name__}: {exc}")

    role      = _norm_role(row.get("role"))
    agency_id = (row.get("agency_id") or "").strip() or None

    if role == ROLE_PLATFORM_ADMIN:
        return Principal(email, role, agency_id, None, all_cities=True)

    agency_cities = _agency_cities(repo, agency_id)

    if role == ROLE_AGENCY_ADMIN:
        # Implicitly holds every city the agency has been granted.
        return Principal(email, role, agency_id, agency_cities, all_cities=False)

    # viewer — granted a subset, always bounded by the agency's current grant.
    granted = _load_cities(row.get("cities") or row.get("city"))
    if agency_id:
        granted &= agency_cities
    return Principal(email, ROLE_VIEWER, agency_id, granted, all_cities=False)


def _agency_cities(repo: Any, agency_id: Optional[str]) -> Set[str]:
    if not agency_id:
        return set()
    try:
        agency = repo.get_agency(agency_id)
    except Exception:
        agency = None
    if not agency:
        return set()
    return _load_cities(agency.get("granted_cities"))


# ── Scoping helpers ──────────────────────────────────────────────────────────

def visible_cities(principal: Principal) -> Optional[Set[str]]:
    """Return the set of cities the principal may see, or None for ALL."""
    return None if principal.all_cities else principal.cities


def filter_rows(rows: List[Dict[str, Any]], principal: Principal,
                city_key: str = "city") -> List[Dict[str, Any]]:
    """Keep only rows whose city the principal may see."""
    if principal.all_cities:
        return rows
    allowed = principal.cities
    return [r for r in rows if r.get(city_key) in allowed]


def scope_requested_cities(requested: Optional[List[str]],
                           principal: Principal) -> List[str]:
    """Intersect a caller's requested city list with what they may audit.

    None/empty request => all of the principal's cities (or all cities if
    platform admin, signalled by returning None).
    """
    if principal.all_cities:
        return requested or []      # [] => caller wants everything (all targets)
    allowed = principal.cities
    if not requested:
        return sorted(allowed)
    return [c for c in requested if c in allowed]


# ── Delegated administration bounds ──────────────────────────────────────────

class AccessDenied(Exception):
    """Raised when an actor attempts an action outside their delegation scope."""


def assert_can_manage_user(actor: Principal, *, target_email: str,
                           target_role: str, target_agency_id: Optional[str],
                           target_cities: List[str], repo: Any) -> None:
    """Enforce who may create/modify a user with the given attributes.

    Platform admin: unrestricted.
    Agency admin: only within their own agency, only roles viewer|agency_admin,
                  and only granting cities their agency actually holds.
    Anyone else: denied.
    """
    role = _norm_role(target_role)

    if actor.is_platform_admin:
        if role not in VALID_ROLES:
            raise AccessDenied(f"Invalid role: {target_role}")
        return

    if not actor.is_agency_admin:
        raise AccessDenied("You do not have permission to manage users.")

    # Agency admins operate strictly inside their own agency.
    if not actor.agency_id:
        raise AccessDenied("Your account is not attached to an agency.")
    if target_agency_id and target_agency_id != actor.agency_id:
        raise AccessDenied("You can only manage users within your own agency.")
    if role == ROLE_PLATFORM_ADMIN:
        raise AccessDenied("Agency admins cannot grant platform-admin access.")
    if role not in (ROLE_VIEWER, ROLE_AGENCY_ADMIN):
        raise AccessDenied(f"Invalid role: {target_role}")

    # Can only grant cities the agency itself holds.
    agency_grant = _agency_cities(repo, actor.agency_id)
    over = set(target_cities) - agency_grant
    if over:
        raise AccessDenied(
            "You can only grant cities your agency holds. "
            f"Not in your agency's grant: {', '.join(sorted(over))}")


def assert_can_manage_agency(actor: Principal) -> None:
    """Only platform admins create agencies or change their city grants."""
    if not actor.is_platform_admin:
        raise AccessDenied("Only platform administrators can manage agencies.")
