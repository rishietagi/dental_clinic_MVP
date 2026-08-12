"""Visit recording endpoints (step 4.3).

Where the app starts holding real clinical content. The **second role-split
resource** after the 4.1 catalogue (BUILD_PLAN §2):

- **Writes** — `require_role("dentist", "admin")`. Recording visits and clinical
  notes is the Dentist's job; the Receptionist books and bills but does not write
  the clinical record. Enforced HERE, on the API.
- **Reads** — any active staff. The receptionist needs visit history for billing
  (5.2) and to book follow-ups.

**One request = one sitting = one transaction.** Recording a visit can write three
tables (an auto-created `treatment`, the `visit`, its `procedure_performed` rows).
They must all land or none of them: a visit that saved without its procedures is a
clinical record that silently lost what was done to the patient. So everything is
built in the session, flushed to assign ids, audited, and committed exactly once.
For the same reason every `treatment_item_id` is validated up front — an unknown
item returns 404 with nothing written, rather than a half-built visit and a 500
from the FK.

The auto-create/auto-close rule itself lives in `services/visits.py`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.invoice import Invoice
from app.models.patient import Patient
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.schemas.visit import (
    ClinicalRecord,
    ProcedureRead,
    TreatmentSummary,
    UnbilledVisit,
    UnbilledVisitsResponse,
    VisitCreate,
    VisitListResponse,
    VisitRead,
    VisitUpdate,
)
from app.services.audit import record_audit
from app.services.visits import (
    TreatmentAlreadyClosed,
    TreatmentNotFound,
    TreatmentPatientMismatch,
    close_appointment_for_visit,
    resolve_treatment,
)

router = APIRouter(prefix="/visits", tags=["visits"])


def _get_or_404(db: Session, visit_id: UUID) -> Visit:
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found."
        )
    return visit


def _load_procedures(db: Session, visit_id: UUID) -> list[ProcedureRead]:
    """A visit's procedures with catalogue names resolved (one joined query)."""
    rows = db.execute(
        select(ProcedurePerformed, TreatmentItem.name)
        .join(TreatmentItem, ProcedurePerformed.treatment_item_id == TreatmentItem.id)
        .where(ProcedurePerformed.visit_id == visit_id)
        .order_by(TreatmentItem.name)
    ).all()
    return [
        ProcedureRead(
            id=proc.id,
            treatment_item_id=proc.treatment_item_id,
            treatment_item_name=name,
            tooth_ref=proc.tooth_ref,
        )
        for proc, name in rows
    ]


def _dentist_name(db: Session, dentist_id: UUID | None) -> str | None:
    if dentist_id is None:
        return None
    who = db.get(StaffUser, dentist_id)
    return who.name if who is not None else None


# The OPD card's field names, taken from the schema rather than re-typed here.
# Copying twenty column names by hand into both the reader and the writer is how
# a field silently stops being saved; deriving them means adding one to
# `ClinicalRecord` wires it through both paths automatically (6.10).
_CLINICAL_FIELDS = tuple(ClinicalRecord.model_fields)


def _to_read(db: Session, visit: Visit) -> VisitRead:
    """Assemble the full visit response: the sitting + its thread + what was done."""
    treatment = db.get(Treatment, visit.treatment_id)
    return VisitRead(
        id=visit.id,
        number=visit.number,
        patient_id=visit.patient_id,
        treatment_id=visit.treatment_id,
        appointment_id=visit.appointment_id,
        dentist_id=visit.dentist_id,
        dentist_name=_dentist_name(db, visit.dentist_id),
        consulting_dentist_id=visit.consulting_dentist_id,
        consulting_dentist_name=_dentist_name(db, visit.consulting_dentist_id),
        visit_date=visit.visit_date,
        complaint=visit.complaint,
        clinical_notes=visit.clinical_notes,
        created_at=visit.created_at,
        updated_at=visit.updated_at,
        treatment=TreatmentSummary.model_validate(treatment),
        procedures=_load_procedures(db, visit.id),
        **{f: getattr(visit, f) for f in _CLINICAL_FIELDS},
    )


def _validate_items(db: Session, body: VisitCreate) -> None:
    """Reject unknown catalogue items BEFORE anything is written.

    Letting a bad id reach the FK would mean a rolled-back half-built visit and a
    500; this gives a clear 404 and leaves the DB untouched. Retired (inactive)
    items are still accepted — a procedure genuinely performed with an item that
    was later retired must remain recordable.
    """
    wanted = {p.treatment_item_id for p in body.procedures}
    if not wanted:
        return

    found = set(
        db.scalars(
            select(TreatmentItem.id).where(TreatmentItem.id.in_(wanted))
        ).all()
    )
    missing = wanted - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown treatment item(s): {', '.join(sorted(str(m) for m in missing))}.",
        )


@router.post("", response_model=VisitRead, status_code=status.HTTP_201_CREATED)
def create_visit(
    body: VisitCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> VisitRead:
    """Record a sitting, creating (and optionally closing) its treatment.

    The schema guarantees exactly one of `treatment_id` / `treatment` was given.
    A single-visit cleaning arrives as a stub + `treatment_status="completed"` and
    comes back as a closed treatment with one visit — one call, nothing dangling.

    An archived patient is refused (6.13) — the same rule patient_files.py has had
    since 5.6, applied consistently. Unarchive first if they really are back.
    """
    patient = db.get(Patient, body.patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
        )
    if patient.archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot record a visit for an archived patient.",
        )

    _validate_items(db, body)

    try:
        treatment, treatment_created = resolve_treatment(
            db,
            patient_id=body.patient_id,
            treatment_id=body.treatment_id,
            stub=body.treatment,
            status=body.treatment_status,
        )
    except TreatmentNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Treatment not found."
        ) from exc
    except TreatmentPatientMismatch as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That treatment belongs to a different patient.",
        ) from exc
    except TreatmentAlreadyClosed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That treatment is already completed. Reopen it before adding a visit.",
        ) from exc

    # A consulting dentist, if given, must be a real active staff member.
    if body.consulting_dentist_id is not None:
        who = db.get(StaffUser, body.consulting_dentist_id)
        if who is None or not who.active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Consulting dentist is not an active staff member.",
            )

    visit = Visit(
        patient_id=body.patient_id,
        treatment_id=treatment.id,
        appointment_id=body.appointment_id,
        dentist_id=body.dentist_id if body.dentist_id is not None else staff.id,
        consulting_dentist_id=body.consulting_dentist_id,
        complaint=body.complaint,
        clinical_notes=body.clinical_notes,
        # The OPD card's fields, all optional (6.10).
        **{f: getattr(body, f) for f in _CLINICAL_FIELDS},
    )
    if body.visit_date is not None:
        visit.visit_date = body.visit_date

    db.add(visit)
    db.flush()  # assign visit.id for the procedure FKs

    for p in body.procedures:
        db.add(
            ProcedurePerformed(
                visit_id=visit.id,
                treatment_item_id=p.treatment_item_id,
                tooth_ref=p.tooth_ref,
            )
        )

    # Auto-creation is recorded explicitly so a treatment that appeared without
    # anyone asking for one is traceable in the audit trail.
    if treatment_created:
        record_audit(
            db,
            actor_id=staff.id,
            action="create",
            entity="treatment",
            entity_id=treatment.id,
            details=jsonable_encoder(
                {
                    "title": treatment.title,
                    "tooth_ref": treatment.tooth_ref,
                    "status": treatment.status,
                    "auto_created_by_visit": True,
                }
            ),
        )

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="visit",
        entity_id=visit.id,
        details=jsonable_encoder(
            {
                "patient_id": body.patient_id,
                "treatment_id": treatment.id,
                "treatment_status": body.treatment_status,
                "procedure_count": len(body.procedures),
            }
        ),
    )

    # Recording the sitting finishes the appointment (6.8) — in THIS transaction,
    # so the clinical record and the calendar can never disagree. Skipped for
    # walk-ins and for terminal statuses; audited only when it actually changed,
    # so the trail shows a real state change rather than a no-op on every visit.
    if close_appointment_for_visit(db, body.appointment_id):
        record_audit(
            db,
            actor_id=staff.id,
            action="status",
            entity="appointment",
            entity_id=body.appointment_id,
            details=jsonable_encoder(
                {"status": "done", "auto_closed_by_visit": True, "visit_id": visit.id}
            ),
        )

    # The single commit: treatment, visit, procedures, appointment and audit rows.
    db.commit()
    db.refresh(visit)
    return _to_read(db, visit)


@router.get("/unbilled", response_model=UnbilledVisitsResponse)
def list_unbilled_visits(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> UnbilledVisitsResponse:
    """Recorded visits that have no invoice yet — the "to bill" worklist (6.8).

    Treatment that was carried out but never billed is revenue walking out of
    the door, and until 6.8 **no screen in the app could show it**: billing was
    reachable only by remembering to click through from the one visit you had
    just recorded. The dev database had 9 of these sitting invisible.

    Any active staff — billing is front-desk work (the 5.2 rule).

    **Declared BEFORE `GET /{visit_id}`** or FastAPI parses "unbilled" as a visit
    UUID and 422s. Same discipline as `/treatments/needs-follow-up` (4.8),
    `/invoices/collections` (5.5) and `/lab-cases/dashboard` (6.6); a test pins it.
    """
    dentist = aliased(StaffUser)

    # LEFT JOIN ... WHERE NULL: the visits with no matching invoice row.
    base = (
        select(Visit, Patient.name, Treatment.title, dentist.name)
        .join(Patient, Visit.patient_id == Patient.id)
        .join(Treatment, Visit.treatment_id == Treatment.id)
        .outerjoin(dentist, Visit.dentist_id == dentist.id)
        .outerjoin(Invoice, Invoice.visit_id == Visit.id)
        .where(Invoice.id.is_(None))
    )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(base.order_by(Visit.visit_date.desc()).limit(limit)).all()

    items = [
        UnbilledVisit(
            id=visit.id,
            patient_id=visit.patient_id,
            patient_name=patient_name,
            treatment_title=title,
            visit_date=visit.visit_date,
            dentist_name=dentist_name,
            procedure_count=db.scalar(
                select(func.count())
                .select_from(ProcedurePerformed)
                .where(ProcedurePerformed.visit_id == visit.id)
            )
            or 0,
        )
        for visit, patient_name, title, dentist_name in rows
    ]
    return UnbilledVisitsResponse(items=items, total=total)


@router.get("", response_model=VisitListResponse)
def list_visits(
    patient_id: UUID | None = Query(default=None),
    treatment_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> VisitListResponse:
    """Visits for one patient OR one treatment, newest first.

    Exactly one filter is required — an unfiltered dump of every visit in the
    clinic isn't a use case any screen has, and it would be a lot of clinical
    data to hand out in one response.
    """
    if (patient_id is None) == (treatment_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide exactly one of 'patient_id' or 'treatment_id'.",
        )

    base = select(Visit)
    if patient_id is not None:
        base = base.where(Visit.patient_id == patient_id)
    else:
        base = base.where(Visit.treatment_id == treatment_id)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Visit.visit_date.desc())).all()

    return VisitListResponse(
        items=[_to_read(db, v) for v in rows],
        total=total,
    )


@router.get("/{visit_id}", response_model=VisitRead)
def get_visit(
    visit_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> VisitRead:
    return _to_read(db, _get_or_404(db, visit_id))


@router.patch("/{visit_id}", response_model=VisitRead)
def update_visit(
    visit_id: UUID,
    body: VisitUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> VisitRead:
    """Correct a visit's notes, complaint or date.

    Cannot re-thread a visit onto another treatment or patient (see VisitUpdate),
    and does not touch the treatment's status — closing/reopening is 4.5.
    """
    visit = _get_or_404(db, visit_id)

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return _to_read(db, visit)

    for field, value in changes.items():
        setattr(visit, field, value)

    record_audit(
        db,
        actor_id=staff.id,
        action="update",
        entity="visit",
        entity_id=visit.id,
        details=jsonable_encoder(changes),
    )
    db.commit()
    db.refresh(visit)
    return _to_read(db, visit)
