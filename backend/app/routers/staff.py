"""Staff directory endpoint (step 6.3).

A small read so the frontend can populate **dentist dropdowns** (primary +
consulting dentist on the booking and visit screens). Before this there was no way
to list staff — `/me` only returns the signed-in user.

Any active staff may read it (names, not patient data — no PII concern). It filters
to `active` staff and, optionally, to a role (`?role=dentist`) so the booking form
only offers people who can be a dentist on an appointment.

This lists `staff_user` rows — our authorization table. Creating a real *login* for
a new staff member is a Supabase Auth concern and is out of scope here; this just
surfaces the staff records that appointments/visits reference.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.staff_user import StaffUser
from app.schemas.staff import StaffListResponse, StaffSummary

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("", response_model=StaffListResponse)
def list_staff(
    role: str | None = Query(
        default=None,
        description="Optional role filter, e.g. 'dentist'. Omit for all active staff.",
    ),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> StaffListResponse:
    """Active staff, newest-first-name order, optionally filtered by role."""
    stmt = select(StaffUser).where(StaffUser.active.is_(True))
    if role is not None:
        # roles is a Postgres text[]; `.any()` matches membership.
        stmt = stmt.where(StaffUser.roles.any(role))
    stmt = stmt.order_by(StaffUser.name)

    rows = db.scalars(stmt).all()
    return StaffListResponse(
        items=[StaffSummary.model_validate(s) for s in rows],
        total=len(rows),
    )
