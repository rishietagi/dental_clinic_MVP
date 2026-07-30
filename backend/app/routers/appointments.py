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

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.auth import get_current_staff
from app.db import get_db
from app.models.appointment import Appointment
from app.models.clinic_settings import ClinicSettings
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.models.visit import Visit
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
from app.services.clinic import clinic_day_bounds

router = APIRouter(prefix="/appointments", tags=["appointments"])

_OVERLAP_DETAIL = "This time slot overlaps an existing appointment."


def _clinic_timezone(db: Session) -> str:
    """The clinic's IANA timezone from settings, falling back to UTC.

    The migration seeds the settings row, so the fallback only matters in the
    theoretical case it's missing — better a UTC-bounded day than a 500 on a
    read.
    """
    settings = db.get(ClinicSettings, 1)
    return settings.timezone if settings is not None else "UTC"


def _get_or_404(db: Session, appointment_id: UUID) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if appt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found."
        )
    return appt


def _validate_dentist(db: Session, dentist_id: UUID | None, *, field: str) -> None:
    """Reject a dentist id that isn't a real, active staff member (422).

    Both dentist fields (primary + consulting) go through this. A NULL is fine
    (both are optional). An unknown/inactive id is a clear 422 rather than a raw FK
    error or a dangling reference.
    """
    if dentist_id is None:
        return
    who = db.get(StaffUser, dentist_id)
    if who is None or not who.active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} is not an active staff member.",
        )


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
    _validate_dentist(db, body.dentist_id, field="Dentist")
    _validate_dentist(db, body.consulting_dentist_id, field="Consulting dentist")

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
    patient_id: UUID | None = Query(
        default=None, description="This patient's appointments (no date needed)."
    ),
    missing_visit: bool = Query(
        default=False, description="Only 'done' appointments with no visit recorded."
    ),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> AppointmentListResponse:
    """Appointments in a day, a date range, OR for one patient.

    Three forms — pass EXACTLY one of the first two, or `patient_id`:
    - `date=YYYY-MM-DD` → that single day (the day-view calendar).
    - `from=…&to=…` → the inclusive range from `from` 00:00 to `to` 23:59 (the
      week-view calendar).
    - `patient_id=…` → **that patient's whole history, newest first (6.8)**, with
      no date at all. The patient profile needs "when are they next in?" and
      "when were they last here?", which neither date form can answer without the
      caller already knowing the date.

    `missing_visit=true` narrows to appointments marked `done` that have **no
    visit recorded** — the dashboard's "nothing recorded" nudge. That state is
    genuinely ambiguous (was the patient treated, or did the dentist forget to
    write it up?), so it is surfaced rather than left to rot.

    Dates and the patient's own id in the path-free query are fine here: a
    `patient_id` on this endpoint is the *filter subject*, and the no-identifiers
    rule is about leaking a patient's identity into a URL that names them — this
    returns nothing a caller didn't already have the id for.
    """
    by_patient = patient_id is not None

    if by_patient:
        if date_ is not None or from_ is not None or to is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Pass either `patient_id` or a date form, not both.",
            )
        range_start = range_end = None
    elif date_ is not None:
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
            detail="Pass `date`, both `from` and `to`, or `patient_id`.",
        )

    # Join the patient (always present), the primary dentist, and the consulting
    # dentist (both nullable → outerjoins, the consulting one via an ALIAS since we
    # join staff_user twice) so each row carries the names the calendar needs — one
    # query, no N+1.
    consulting = aliased(StaffUser)
    stmt = (
        select(Appointment, Patient.name, StaffUser.name, consulting.name)
        .join(Patient, Appointment.patient_id == Patient.id)
        .outerjoin(StaffUser, Appointment.dentist_id == StaffUser.id)
        .outerjoin(consulting, Appointment.consulting_dentist_id == consulting.id)
    )

    if by_patient:
        # Newest first: "when are they next in / when were they last here" reads
        # better most-recent-down than in calendar order.
        stmt = stmt.where(Appointment.patient_id == patient_id).order_by(
            Appointment.start_time.desc()
        )
    else:
        # "A day" is a CLINIC-local day, not a UTC day. Read the clinic timezone
        # and bound the range in it (4.9). For an IST clinic, 2 Aug means 2 Aug
        # 00:00 IST → 2 Aug 23:59 IST, i.e. 1 Aug 18:30 UTC → 2 Aug 18:29 UTC — so
        # evening IST appointments (previous UTC day) are correctly included.
        tz_name = _clinic_timezone(db)
        day_start, _ = clinic_day_bounds(range_start, tz_name)
        _, day_end = clinic_day_bounds(range_end, tz_name)
        stmt = (
            stmt.where(Appointment.start_time >= day_start)
            .where(Appointment.start_time <= day_end)
            .order_by(Appointment.start_time)
        )

    if missing_visit:
        # Finished, but nothing was written up. LEFT JOIN ... WHERE NULL.
        stmt = stmt.outerjoin(Visit, Visit.appointment_id == Appointment.id).where(
            Appointment.status == "done", Visit.id.is_(None)
        )

    rows = db.execute(stmt).all()

    items = [
        AppointmentListItem(
            id=appt.id,
            number=appt.number,
            patient_id=appt.patient_id,
            patient_name=patient_name,
            dentist_id=appt.dentist_id,
            dentist_name=dentist_name,
            consulting_dentist_id=appt.consulting_dentist_id,
            consulting_dentist_name=consulting_name,
            treatment_id=appt.treatment_id,
            start_time=appt.start_time,
            duration_min=appt.duration_min,
            status=appt.status,
            reason=appt.reason,
        )
        for appt, patient_name, dentist_name, consulting_name in rows
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

    if "dentist_id" in changes:
        _validate_dentist(db, changes["dentist_id"], field="Dentist")
    if "consulting_dentist_id" in changes:
        _validate_dentist(db, changes["consulting_dentist_id"], field="Consulting dentist")

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
