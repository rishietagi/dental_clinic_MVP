"""Authentication & authorization dependencies.

The chain, from raw request to an authorized staff member:

    get_current_claims   verify the Supabase JWT (ES256, via JWKS) -> claims dict
        │
    get_current_staff    claims["sub"] -> staff_user row (must exist + be active)
        │
    require_role(*roles) staff must hold at least one of the given roles

Roles come from OUR database (staff_user.roles), never from the token — the
token's `role` claim is the Postgres role ("authenticated"), not an app role.
Fetching roles from the DB means deactivating a user or changing their roles
takes effect immediately, without waiting for a new token to be issued.
"""

from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.staff_user import StaffUser

# Supabase access tokens are asymmetric (ES256). We only ever hold the PUBLIC
# keys, fetched from the project's JWKS endpoint.
_ALGORITHMS = ["ES256"]
_AUDIENCE = "authenticated"

# Extracts the "Authorization: Bearer <token>" header. auto_error=True makes it
# return 401 automatically when the header is missing or malformed.
_bearer = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    """One cached JWKS client (it caches keys and refreshes on an unknown kid).

    Built lazily so the app imports fine without SUPABASE_URL set; only a request
    that actually needs to verify a token will trip the config check.
    """
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL is not configured on the server.",
        )
    return PyJWKClient(settings.supabase_jwks_url)


def get_current_claims(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """Verify the bearer token's signature + issuer + audience + expiry."""
    token = credentials.credentials
    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALGORITHMS,
            audience=_AUDIENCE,
            issuer=settings.supabase_issuer,
        )
    except HTTPException:
        raise  # config error from _jwk_client() — pass through unchanged
    except jwt.PyJWTError as exc:
        # Expired, bad signature, wrong issuer/audience, unknown key, etc.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_staff(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> StaffUser:
    """Map a verified token to the staff_user row it belongs to.

    A valid Supabase token means "authenticated" — it does NOT mean "is staff
    here". A user with no staff_user row (or a deactivated one) is rejected.
    """
    sub = claims.get("sub")
    try:
        staff_id = UUID(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no valid subject.",
        ) from exc

    staff = db.get(StaffUser, staff_id)
    if staff is None or not staff.active:
        # Authenticated in Supabase, but not a provisioned/active staff member.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an active staff member.",
        )
    return staff


def require_role(*allowed: str):
    """Build a dependency that requires at least one of `allowed` roles.

    Usage:  Depends(require_role("admin"))  /  Depends(require_role("dentist", "admin"))
    Returns the StaffUser so handlers can use it.
    """
    allowed_set = set(allowed)

    def _require(staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
        if not allowed_set.intersection(staff.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of these roles: {', '.join(sorted(allowed_set))}.",
            )
        return staff

    return _require
