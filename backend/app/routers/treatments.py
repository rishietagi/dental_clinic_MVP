"""Treatment endpoints — reads (4.4) + lifecycle close/reopen (4.5).

The reads (`GET /treatments`, `GET /{id}`) exist because the visit record screen
has to offer the dentist the patient's *open* treatments to continue ("sitting 2
of the RCT") versus starting new work. Reads are any active staff and unaudited.

The lifecycle writes (4.5) let the dentist **close** a treatment without recording
a visit, and **reopen** a completed one — the remedy for the 409 the visit form
hits against a closed treatment (4.4). They're role-split like visit recording
(`require_role("dentist","admin")`): closing a course of treatment is a clinical
judgement, not a front-desk action (BUILD_PLAN §2). There is still **no create or
replace** — treatments are born from `POST /visits`; these two are the only writes.

The tiny state machine (`in_progress <-> completed`) lives in
`services/treatments.py`; an illegal transition is a 409, mirroring the
appointment status workflow (3.5). Each transition is audited.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.schemas.treatment import TreatmentListResponse, TreatmentRead
from app.services.audit import record_audit
from app.services.treatments import (
    IllegalTreatmentTransition,
    close_treatment,
    reopen_treatment,
)

router = APIRouter(prefix="/treatments", tags=["treatments"])


def _get_or_404(db: Session, treatment_id: UUID) -> Treatment:
    treatment = db.get(Treatment, treatment_id)
    if treatment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Treatment not found."
        )
    return treatment


@router.get("", response_model=TreatmentListResponse)
def list_treatments(
    patient_id: UUID = Query(description="Whose treatments to list."),
    status_filter: Literal["in_progress", "completed"] | None = Query(
        default=None,
        alias="status",
        description="Optional filter. Omit for all of this patient's treatments.",
    ),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> TreatmentListResponse:
    """One patient's treatments — open ones first, then most recent.

    `patient_id` is required: an unfiltered list of every treatment in the clinic
    isn't a screen anyone has, and the visit form always asks about one patient.

    The ordering puts `in_progress` first because every caller so far is looking
    for actionable work — the visit form's "continue this treatment" picker, and
    4.8's open-treatments report.
    """
    base = select(Treatment).where(Treatment.patient_id == patient_id)
    if status_filter is not None:
        base = base.where(Treatment.status == status_filter)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    # Open treatments sort first (0), everything else after (1); newest first
    # within each group.
    open_first = case((Treatment.status == "in_progress", 0), else_=1)
    rows = db.scalars(
        base.order_by(open_first, Treatment.started_at.desc())
    ).all()

    return TreatmentListResponse(
        items=[TreatmentRead.model_validate(t) for t in rows],
        total=total,
    )


@router.get("/{treatment_id}", response_model=TreatmentRead)
def get_treatment(
    treatment_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> Treatment:
    return _get_or_404(db, treatment_id)


def _transition(
    treatment_id: UUID,
    action: str,
    apply,  # close_treatment | reopen_treatment
    db: Session,
    staff: StaffUser,
) -> Treatment:
    """Shared close/reopen: load, transition (409 if illegal), audit, commit."""
    treatment = _get_or_404(db, treatment_id)
    old_status = treatment.status

    try:
        apply(treatment)
    except IllegalTreatmentTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action} a treatment that is '{old_status}'.",
        ) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action=action,
        entity="treatment",
        entity_id=treatment.id,
        details={"from": old_status, "to": treatment.status},
    )
    db.commit()
    db.refresh(treatment)
    return treatment


@router.post("/{treatment_id}/close", response_model=TreatmentRead)
def close(
    treatment_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> Treatment:
    """Mark an in-progress treatment complete without recording a visit.

    409 if it's already completed. Sets `closed_at`.
    """
    return _transition(treatment_id, "close", close_treatment, db, staff)


@router.post("/{treatment_id}/reopen", response_model=TreatmentRead)
def reopen(
    treatment_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> Treatment:
    """Reopen a completed treatment (the patient came back).

    409 if it's already in progress. Clears `closed_at`.
    """
    return _transition(treatment_id, "reopen", reopen_treatment, db, staff)
