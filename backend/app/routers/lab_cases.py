"""Lab-case endpoints (step 6.6) — samples sent out to a dental lab.

**Auth: any active staff** for reads AND writes. Sending an impression to a lab and
booking it back in is front-desk work — the receptionist does it, the same call billing
made (5.2). It is not a clinical-record write like visit notes, so it is deliberately
NOT `require_role("dentist", ...)`.

The rules live in `services/lab.py`, which raises domain exceptions; this router maps
them to status codes and owns the transaction + audit rows (the 4.3 pattern).

**Route order matters:** `GET /lab-cases/dashboard` is declared BEFORE
`GET /lab-cases/{case_id}`, or FastAPI parses "dashboard" as a UUID path param and
422s — the same trap `/treatments/needs-follow-up` and `/invoices/collections` document.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.appointment import Appointment
from app.models.lab import Lab
from app.models.lab_case import LabCase
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.schemas.lab import (
    LabCaseCreate,
    LabCaseFollowUp,
    LabCaseListResponse,
    LabCaseRead,
    LabCaseReceive,
    LabDashboard,
)
from app.services.audit import record_audit
from app.services.lab import (
    AppointmentNotFound,
    IllegalLabTransition,
    LabNotFound,
    PatientNotFound,
    VisitNotFound,
    cancel_case,
    create_lab_case,
    lab_dashboard,
    mark_received,
    set_follow_up_done,
)

router = APIRouter(prefix="/lab-cases", tags=["lab-cases"])


def _to_read(case: LabCase, patient_name: str, lab_name: str, appt_number: int | None) -> LabCaseRead:
    """Assemble the display shape — a lab list of UUIDs would be unusable."""
    return LabCaseRead(
        id=case.id,
        number=case.number,
        patient_id=case.patient_id,
        patient_name=patient_name,
        lab_id=case.lab_id,
        lab_name=lab_name,
        visit_id=case.visit_id,
        appointment_id=case.appointment_id,
        appointment_number=appt_number,
        sample_type=case.sample_type,
        tooth_ref=case.tooth_ref,
        sent_date=case.sent_date,
        expected_date=case.expected_date,
        received_date=case.received_date,
        status=case.status,
        follow_up_done=case.follow_up_done,
        notes=case.notes,
        created_at=case.created_at,
    )


def _load_read(db: Session, case_id: UUID) -> LabCaseRead:
    """Re-read one case with its joined names (used after every mutation)."""
    row = db.execute(
        select(LabCase, Patient.name, Lab.name, Appointment.number)
        .join(Patient, LabCase.patient_id == Patient.id)
        .join(Lab, LabCase.lab_id == Lab.id)
        .outerjoin(Appointment, LabCase.appointment_id == Appointment.id)
        .where(LabCase.id == case_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab case not found.")
    case, patient_name, lab_name, appt_number = row
    return _to_read(case, patient_name, lab_name, appt_number)


def _get_or_404(db: Session, case_id: UUID) -> LabCase:
    case = db.get(LabCase, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab case not found.")
    return case


@router.post("", response_model=LabCaseRead, status_code=status.HTTP_201_CREATED)
def create_case(
    body: LabCaseCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabCaseRead:
    """Send a sample to a lab. Any active staff (front-desk work)."""
    try:
        case = create_lab_case(
            db,
            patient_id=body.patient_id,
            lab_id=body.lab_id,
            sample_type=body.sample_type,
            sent_date=body.sent_date,
            expected_date=body.expected_date,
            visit_id=body.visit_id,
            appointment_id=body.appointment_id,
            tooth_ref=body.tooth_ref,
            notes=body.notes,
            created_by=staff.id,
        )
    except PatientNotFound as exc:
        raise HTTPException(status_code=404, detail="Patient not found.") from exc
    except LabNotFound as exc:
        raise HTTPException(status_code=404, detail="Lab not found.") from exc
    except VisitNotFound as exc:
        raise HTTPException(status_code=404, detail="Visit not found.") from exc
    except AppointmentNotFound as exc:
        raise HTTPException(status_code=404, detail="Appointment not found.") from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="lab_case",
        entity_id=case.id,
        details=jsonable_encoder(
            {
                "number": case.number,
                "patient_id": body.patient_id,
                "lab_id": body.lab_id,
                "sample_type": body.sample_type,
                "sent_date": body.sent_date,
                "expected_date": body.expected_date,
            }
        ),
    )
    db.commit()
    return _load_read(db, case.id)


@router.get("", response_model=LabCaseListResponse)
def list_cases(
    status_filter: str | None = Query(
        default=None, alias="status", description="sent / received / cancelled."
    ),
    patient_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabCaseListResponse:
    """Lab cases, newest first, with patient + lab names resolved."""
    base = select(LabCase)
    if status_filter is not None:
        base = base.where(LabCase.status == status_filter)
    if patient_id is not None:
        base = base.where(LabCase.patient_id == patient_id)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.execute(
        base.add_columns(Patient.name, Lab.name, Appointment.number)
        .join(Patient, LabCase.patient_id == Patient.id)
        .join(Lab, LabCase.lab_id == Lab.id)
        .outerjoin(Appointment, LabCase.appointment_id == Appointment.id)
        .order_by(LabCase.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return LabCaseListResponse(
        items=[_to_read(c, pn, ln, an) for c, pn, ln, an in rows],
        total=total,
    )


@router.get("/dashboard", response_model=LabDashboard)
def get_dashboard(
    due_within_days: int = Query(default=7, ge=1, le=60),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabDashboard:
    """Overdue / due-soon / back-from-lab — the three lists the dashboard shows.

    Declared BEFORE `/{case_id}`, or "dashboard" would be parsed as a UUID (422).
    """
    buckets = lab_dashboard(db, due_within_days=due_within_days)
    return LabDashboard(
        overdue=[_to_read(c, pn, ln, an) for c, pn, ln, an in buckets["overdue"]],
        due_soon=[_to_read(c, pn, ln, an) for c, pn, ln, an in buckets["due_soon"]],
        back_from_lab=[_to_read(c, pn, ln, an) for c, pn, ln, an in buckets["back_from_lab"]],
    )


@router.get("/{case_id}", response_model=LabCaseRead)
def get_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabCaseRead:
    return _load_read(db, case_id)


@router.post("/{case_id}/received", response_model=LabCaseRead)
def receive_case(
    case_id: UUID,
    body: LabCaseReceive,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabCaseRead:
    """Mark a case back from the lab (defaults to the clinic's today)."""
    case = _get_or_404(db, case_id)
    try:
        mark_received(db, case, body.received_date)
    except IllegalLabTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That case isn't at the lab — it's already back or cancelled.",
        ) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="received",
        entity="lab_case",
        entity_id=case.id,
        details=jsonable_encoder({"received_date": case.received_date}),
    )
    db.commit()
    return _load_read(db, case_id)


@router.post("/{case_id}/cancel", response_model=LabCaseRead)
def cancel(
    case_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabCaseRead:
    case = _get_or_404(db, case_id)
    try:
        cancel_case(db, case)
    except IllegalLabTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a case still at the lab can be cancelled.",
        ) from exc

    record_audit(db, actor_id=staff.id, action="cancel", entity="lab_case", entity_id=case.id)
    db.commit()
    return _load_read(db, case_id)


@router.post("/{case_id}/follow-up-done", response_model=LabCaseRead)
def follow_up_done(
    case_id: UUID,
    body: LabCaseFollowUp,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabCaseRead:
    """Tick off the 'call the patient in' nudge for a returned case."""
    case = _get_or_404(db, case_id)
    set_follow_up_done(case, body.done)
    record_audit(
        db,
        actor_id=staff.id,
        action="follow_up_done",
        entity="lab_case",
        entity_id=case.id,
        details=jsonable_encoder({"done": body.done}),
    )
    db.commit()
    return _load_read(db, case_id)
