"""Staff identity — WITHOUT authentication (step 10.1).

**This app no longer authenticates anyone.** It runs as a packaged desktop app on
a single PC at the clinic's front desk, used by one person at a time, behind
Windows' own login. There is no server, no network exposure, and no second user
to tell apart. A login screen would be theatre, and — worse — the previous one
(Supabase Auth) was a *cloud* service, so it made an otherwise offline app stop
working whenever the clinic's internet did.

    get_current_claims   -> {"sub": <the local staff id>}   (no token, no network)
        │
    get_current_staff    claims["sub"] -> staff_user row (must exist + be active)
        │
    require_role(*roles) ALWAYS PASSES — kept only so call sites need no edits

WHY THE SHAPE IS UNCHANGED
    Every router still declares `Depends(get_current_staff)` or
    `Depends(require_role(...))`, and every test still overrides
    `get_current_claims`. Keeping those three names and signatures is what made
    this a ~50-line change instead of a 35-file one.

WHAT STILL WORKS, AND WHY IT MATTERS
    A REAL `staff_user` row is still resolved and returned, so everything that
    hangs off staff identity keeps working exactly as before:
      - `audit_log.actor_id` — who did what, still recorded (medico-legal)
      - `visit.dentist_id` / `appointment.dentist_id` — attribution
      - by-dentist reporting (6.5)
    Dentists remain name-only RECORDS (6.5) — they were never logins, so nothing
    about assigning or attributing them changes.

WHAT WAS DELIBERATELY REMOVED
    JWT verification (ES256 via JWKS), the Supabase dependency, and the role
    gates added in 6.12. `require_role` is now a no-op that returns the same
    staff member. It is kept rather than deleted so that (a) call sites read the
    same, (b) the intent stays documented at each endpoint, and (c) restoring
    real auth later means changing this one file back.

    **This reverses step 6.12** (three role logins, reports admin-only), which
    was built two weeks earlier. That is deliberate: 6.12 solved "keep the money
    away from the receptionist" when there were two machines and three logins.
    With one shared machine at the front desk that separation cannot be enforced
    by a login anyway, so the Reports UI is hidden instead (step 10.2).
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.staff_user import StaffUser


def get_current_claims() -> dict:
    """The 'identity' of the only user there is.

    No token, no network, no cryptography — it just names the local staff row.
    Kept as a dependency (rather than inlined) because it is the seam the whole
    test suite overrides to act as a particular staff member.
    """
    return {"sub": settings.local_staff_id}


def get_current_staff(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> StaffUser:
    """Resolve the local staff row that every write is attributed to.

    Still fails loud rather than inventing a user: if the row is missing or
    deactivated the app is misconfigured (the seed never ran, or LOCAL_STAFF_ID
    is wrong), and silently proceeding would write audit rows pointing at nobody.
    """
    sub = claims.get("sub")
    try:
        staff_id = UUID(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "LOCAL_STAFF_ID is not a valid UUID. The app is misconfigured — "
                "run `python -m app.seed`."
            ),
        ) from exc

    staff = db.get(StaffUser, staff_id)
    if staff is None or not staff.active:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The local staff record is missing or inactive. "
                "Run `python -m app.seed` to create it."
            ),
        )
    return staff


def require_role(*allowed: str):
    """No-op role gate — kept for call-site compatibility (10.1).

    Previously enforced `staff.roles`; now every caller is the single local user,
    so there is nobody to refuse. `allowed` is accepted and ignored on purpose:
    it still documents which endpoints *were* privileged, and it means restoring
    real enforcement is a change to this function alone.
    """

    def _require(staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
        return staff

    return _require
