"""Clinic settings endpoints (step 4.9).

The clinic's hours, slot size and timezone. A **role-split** resource like the
treatment catalogue (4.1): any active staff may READ them (the calendar and visit
form need the hours/slot; everything needs the timezone), but only an **admin**
may change them (`require_role("admin")`). The API is the guard; the settings
screen also hides the controls from non-admins, but that's convenience.

There is exactly one settings row, pinned to `id = 1` by a DB CHECK, seeded by
the migration. Both endpoints operate on that row — no create, no delete.

The cross-field rule `close_hour > open_hour` is validated here against the
MERGED row (a PATCH may set only one hour); a violation is a 422 before the DB
CHECK would reject it.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.clinic_settings import ClinicSettings
from app.models.staff_user import StaffUser
from app.schemas.clinic_settings import ClinicSettingsRead, ClinicSettingsUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/clinic-settings", tags=["clinic-settings"])

# The one settings row's primary key (singleton — see the model/migration).
SETTINGS_ID = 1


def _get_settings(db: Session) -> ClinicSettings:
    settings = db.get(ClinicSettings, SETTINGS_ID)
    if settings is None:
        # Should never happen — the migration seeds the row. If it does, it's a
        # server/deploy fault, not a client error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clinic settings row is missing.",
        )
    return settings


@router.get("", response_model=ClinicSettingsRead)
def get_clinic_settings(
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ClinicSettings:
    return _get_settings(db)


@router.patch("", response_model=ClinicSettingsRead)
def update_clinic_settings(
    body: ClinicSettingsUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> ClinicSettings:
    settings = _get_settings(db)

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return settings

    # Validate close > open against the MERGED values (a PATCH may set only one).
    new_open = changes.get("open_hour", settings.open_hour)
    new_close = changes.get("close_hour", settings.close_hour)
    if new_close <= new_open:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="close_hour must be after open_hour.",
        )

    for field, value in changes.items():
        setattr(settings, field, value)

    record_audit(
        db,
        actor_id=staff.id,
        action="update",
        entity="clinic_settings",
        entity_id=None,  # singleton row; no meaningful uuid entity_id
        details=jsonable_encoder(changes),
    )
    db.commit()
    db.refresh(settings)
    return settings
