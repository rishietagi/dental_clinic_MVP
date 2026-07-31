"""Patient CRUD endpoints.

The first real resource API. Every route requires an active staff member
(get_current_staff — receptionist, dentist, or admin all qualify), and every
mutation writes an audit row in the SAME transaction as the change, so the two
commit atomically.

Soft-delete only: archive/unarchive flip the `archived` flag. There is no hard
DELETE — patient records are retained (medico-legal).

Patient ids travel as PATH params (/patients/{id}), never as query strings.
"""

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.schemas.patient import (
    PatientCreate,
    PatientListItem,
    PatientListResponse,
    PatientRead,
    PatientUpdate,
    RecallDueItem,
    RecallDueResponse,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/patients", tags=["patients"])


def _get_or_404(db: Session, patient_id: UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


@router.get("", response_model=PatientListResponse)
def list_patients(
    q: str | None = Query(default=None, description="Search text (matches name or phone)."),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> PatientListResponse:
    """List patients, optionally filtered by a name/phone search.

    Search is a case-insensitive substring match on name OR phone (front desk can
    "type anything"). At clinic scale a plain ILIKE scan is instant — no index
    needed; a pg_trgm GIN index is the escalation path if the table ever grows.
    Archived patients are hidden unless include_archived=true.
    """
    conditions = []
    if not include_archived:
        conditions.append(Patient.archived.is_(False))

    term = (q or "").strip()
    if term:
        pattern = f"%{term}%"
        conditions.append(or_(Patient.name.ilike(pattern), Patient.phone.ilike(pattern)))

    base = select(Patient)
    for cond in conditions:
        base = base.where(cond)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.scalars(
        base.order_by(Patient.name, Patient.created_at).limit(limit).offset(offset)
    ).all()

    return PatientListResponse(
        items=[PatientListItem.model_validate(p) for p in rows],
        total=total,
    )


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: PatientCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Patient:
    patient = Patient(**body.model_dump())
    db.add(patient)
    db.flush()  # assign the id before we audit / return

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="patient",
        entity_id=patient.id,
        details=jsonable_encoder(body.model_dump()),
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/recalls-due", response_model=RecallDueResponse)
def list_recalls_due(
    within_days: int = Query(
        default=0,
        ge=0,
        le=90,
        description="Also include recalls falling due within this many days.",
    ),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> RecallDueResponse:
    """Patients due (or nearly due) a routine check-up — Phase 4 of the workflow.

    A recall is a plain date on the patient, not an appointment: it means "this
    person SHOULD be booked", which is exactly the repeat revenue a paper diary
    loses. Booking them creates a normal appointment; clearing the date takes
    them off this list.

    Archived patients are excluded — chasing someone who has left the practice
    is noise. Soonest-overdue first, so the longest-waiting patient is on top.

    **Declared BEFORE `GET /{patient_id}`** or FastAPI parses "recalls-due" as a
    patient UUID and 422s — the same literal-before-`{id}` discipline as
    `/treatments/needs-follow-up` (4.8), `/invoices/collections` (5.5),
    `/lab-cases/dashboard` (6.6) and `/visits/unbilled` (6.8). A test pins it.
    """
    cutoff = date.today() + timedelta(days=within_days)

    base = select(Patient).where(
        Patient.archived.is_(False),
        Patient.recall_due.is_not(None),
        Patient.recall_due <= cutoff,
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Patient.recall_due, Patient.name)).all()

    return RecallDueResponse(
        items=[RecallDueItem.model_validate(p) for p in rows],
        total=total,
    )


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(
    patient_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Patient:
    # Archived patients are still returned — they're hidden from lists, not deleted.
    return _get_or_404(db, patient_id)


@router.patch("/{patient_id}", response_model=PatientRead)
def update_patient(
    patient_id: UUID,
    body: PatientUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Patient:
    patient = _get_or_404(db, patient_id)

    # exclude_unset: only fields the caller actually sent are changed. A field set
    # to null IS a change (clears it); an omitted field is left alone.
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        # Nothing to do — don't write an empty audit row.
        return patient

    for field, value in changes.items():
        setattr(patient, field, value)

    record_audit(
        db,
        actor_id=staff.id,
        action="update",
        entity="patient",
        entity_id=patient.id,
        details=jsonable_encoder(changes),
    )
    db.commit()
    db.refresh(patient)
    return patient


def _set_archived(
    patient_id: UUID, archived: bool, db: Session, staff: StaffUser
) -> Patient:
    patient = _get_or_404(db, patient_id)
    patient.archived = archived
    record_audit(
        db,
        actor_id=staff.id,
        action="archive" if archived else "unarchive",
        entity="patient",
        entity_id=patient.id,
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.post("/{patient_id}/archive", response_model=PatientRead)
def archive_patient(
    patient_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Patient:
    """Soft-delete: hide the patient from active lists. Never removes the row."""
    return _set_archived(patient_id, True, db, staff)


@router.post("/{patient_id}/unarchive", response_model=PatientRead)
def unarchive_patient(
    patient_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Patient:
    return _set_archived(patient_id, False, db, staff)
