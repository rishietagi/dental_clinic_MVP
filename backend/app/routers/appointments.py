"""Appointment booking endpoints (step 3.2).

Every route requires an active staff member (any of receptionist/dentist/admin
may book), and every mutation writes an audit row in the SAME transaction as the
change, so the two commit atomically — the patient-router pattern.

Double-booking is prevented at two layers (see app/services/appointments.py):
this router calls find_conflicts() for a friendly 409, and the DB's
`appointment_no_overlap` EXCLUDE constraint is the hard backstop for the race
between two PCs. A constraint violation that slips past the pre-check is
translated to the same 409 rather than surfacing as a 500.

Status transitions (booked → arrived → done, with cancel / no-show off-ramps) go
through a dedicated `POST /{id}/status` endpoint that enforces the state machine
(see app/services/appointments.py). The reschedule PATCH never touches status.
Appointment ids travel as PATH params; the day filter is a query DATE (not a
patient identifier), which the no-id-in-URL rule permits.
"""

from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentListItem,
    AppointmentListResponse,
    AppointmentRead,
    AppointmentStatusUpdate,
    AppointmentUpdate,
)
from app.services.appointments import can_transition, find_conflicts
from app.services.audit import record_audit

router = APIRouter(prefix="/appointments", tags=["appointments"])

_OVERLAP_DETAIL = "This time slot overlaps an existing appointment."


def _get_or_404(db: Session, appointment_id: UUID) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found."
        )
    return appt


def _commit_or_conflict(db: Session) -> None:
    """Commit, translating the no-overlap constraint violation into a 409.

    The service pre-check catches conflicts in the common case; this catches the
    race where two commits interleave past the pre-check. Any other IntegrityError
    (e.g. a bad FK) is re-raised untouched.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "appointment_no_overlap" in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_OVERLAP_DETAIL
            ) from exc
        raise


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: AppointmentCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Appointment:
    # Friendly 404 if the patient doesn't exist, rather than a raw FK error.
    if db.get(Patient, body.patient_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
        )

    conflicts = find_conflicts(
        db,
        dentist_id=body.dentist_id,
        start_time=body.start_time,
        duration_min=body.duration_min,
    )
    if conflicts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_OVERLAP_DETAIL)

    appt = Appointment(**body.model_dump())
    db.add(appt)
    db.flush()  # assign the id before we audit / return

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="appointment",
        entity_id=appt.id,
        details=jsonable_encoder(body.model_dump()),
    )
    _commit_or_conflict(db)
    db.refresh(appt)
    return appt


@router.get("", response_model=AppointmentListResponse)
def list_appointments(
    date_: date | None = Query(default=None, alias="date", description="A single day (YYYY-MM-DD)."),
    from_: date | None = Query(default=None, alias="from", description="Range start (inclusive)."),
    to: date | None = Query(default=None, description="Range end (inclusive)."),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> AppointmentListResponse:
    """Appointments in a day OR a date range, ordered by start time.

    Two mutually exclusive forms — pass EXACTLY one:
    - `date=YYYY-MM-DD` → that single day (the day-view calendar).
    - `from=…&to=…` → the inclusive range from `from` 00:00 to `to` 23:59 (the
      week-view calendar).

    These are query dates, not patient identifiers, so they're fine in the query
    string.
    """
    if date_ is not None:
        if from_ is not None or to is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Pass either `date` or `from`+`to`, not both.",
            )
        range_start, range_end = date_, date_
    elif from_ is not None and to is not None:
        range_start, range_end = from_, to
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Pass either `date` or both `from` and `to`.",
        )

    day_start = datetime.combine(range_start, time.min, tzinfo=timezone.utc)
    day_end = datetime.combine(range_end, time.max, tzinfo=timezone.utc)

    # Join the patient (always present) and the dentist (nullable → outerjoin) so
    # each row carries the names the calendar needs — one query, no N+1.
    rows = db.execute(
        select(Appointment, Patient.name, StaffUser.name)
        .join(Patient, Appointment.patient_id == Patient.id)
        .outerjoin(StaffUser, Appointment.dentist_id == StaffUser.id)
        .where(Appointment.start_time >= day_start)
        .where(Appointment.start_time <= day_end)
        .order_by(Appointment.start_time)
    ).all()

    items = [
        AppointmentListItem(
            id=appt.id,
            patient_id=appt.patient_id,
            patient_name=patient_name,
            dentist_id=appt.dentist_id,
            dentist_name=dentist_name,
            treatment_id=appt.treatment_id,
            start_time=appt.start_time,
            duration_min=appt.duration_min,
            status=appt.status,
            reason=appt.reason,
        )
        for appt, patient_name, dentist_name in rows
    ]

    return AppointmentListResponse(items=items, total=len(items))


@router.get("/{appointment_id}", response_model=AppointmentRead)
def get_appointment(
    appointment_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Appointment:
    return _get_or_404(db, appointment_id)


@router.patch("/{appointment_id}", response_model=AppointmentRead)
def update_appointment(
    appointment_id: UUID,
    body: AppointmentUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Appointment:
    """Reschedule / edit an appointment. Re-runs the conflict check if the timing
    changed (excluding this appointment itself)."""
    appt = _get_or_404(db, appointment_id)

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return appt

    for field, value in changes.items():
        setattr(appt, field, value)

    # Re-check only when something that affects the time span moved.
    if {"start_time", "duration_min", "dentist_id"} & changes.keys():
        conflicts = find_conflicts(
            db,
            dentist_id=appt.dentist_id,
            start_time=appt.start_time,
            duration_min=appt.duration_min,
            exclude_id=appt.id,
        )
        if conflicts:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_OVERLAP_DETAIL
            )

    record_audit(
        db,
        actor_id=staff.id,
        action="update",
        entity="appointment",
        entity_id=appt.id,
        details=jsonable_encoder(changes),
    )
    _commit_or_conflict(db)
    db.refresh(appt)
    return appt


@router.post("/{appointment_id}/status", response_model=AppointmentRead)
def set_status(
    appointment_id: UUID,
    body: AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Appointment:
    """Move an appointment to a new status, enforcing the state machine.

    The status value itself is validated by the schema (unknown → 422). Here we
    reject a *known but illegal* transition (e.g. done → arrived, or no change at
    all) with a 409. Legal transitions are audited.
    """
    appt = _get_or_404(db, appointment_id)

    if not can_transition(appt.status, body.status):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change status from '{appt.status}' to '{body.status}'.",
        )

    old_status = appt.status
    appt.status = body.status
    record_audit(
        db,
        actor_id=staff.id,
        action="status",
        entity="appointment",
        entity_id=appt.id,
        details={"from": old_status, "to": body.status},
    )
    db.commit()
    db.refresh(appt)
    return appt
