"""Patient CRUD endpoints.

The first real resource API. Every route requires an active staff member
(get_current_staff — receptionist, dentist, or admin all qualify), and every
mutation writes an audit row in the SAME transaction as the change, so the two
commit atomically.

Soft-delete only: archive/unarchive flip the `archived` flag. There is no hard
DELETE — patient records are retained (medico-legal).

Patient ids travel as PATH params (/patients/{id}), never as query strings.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/patients", tags=["patients"])


def _get_or_404(db: Session, patient_id: UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")
    return patient


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
