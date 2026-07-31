"""Dental chart endpoints (step 6.11).

**Scope note:** dental charting was listed out of scope in `CLAUDE.md` through
Phase 6 and is built here at the clinic owner's explicit request — a deliberate
addition, like patient file uploads (5.6) and lab tracking (6.6).

Role split follows visits (4.3): **reads are any active staff** (the front desk
needs to see the chart alongside history), **writes are dentist/admin** — what is
wrong with a tooth is a clinical judgement.

The chart is **append-only**; see `services/chart.py` for why. Nothing here
deletes, and there is no PUT/DELETE route to add later by accident.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.models.tooth_condition import ALL_TEETH
from app.schemas.chart import (
    ChartResponse,
    ChartUpdate,
    ToothConditionRead,
    ToothHistoryResponse,
)
from app.services.audit import record_audit
from app.services.chart import UnknownTooth, current_chart, mark_teeth, tooth_history

router = APIRouter(tags=["chart"])


def _patient_or_404(db: Session, patient_id: UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
        )
    return patient


@router.get("/patients/{patient_id}/chart", response_model=ChartResponse)
def get_chart(
    patient_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ChartResponse:
    """This patient's mouth as it stands.

    Only current rows — a tooth with no entry is sound. Superseded findings are
    history and are read per-tooth via `/chart/{tooth}/history`.
    """
    _patient_or_404(db, patient_id)
    rows = current_chart(db, patient_id)
    return ChartResponse(
        patient_id=patient_id,
        items=[ToothConditionRead.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get(
    "/patients/{patient_id}/chart/{tooth}/history",
    response_model=ToothHistoryResponse,
)
def get_tooth_history(
    patient_id: UUID,
    tooth: str,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> ToothHistoryResponse:
    """Everything ever recorded for one tooth, oldest first.

    This is what the append-only model buys: "it was caries in March, filled in
    April" survives, instead of the April finding quietly erasing the March one.
    """
    _patient_or_404(db, patient_id)
    if tooth not in ALL_TEETH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{tooth}' is not an FDI tooth number.",
        )
    rows = tooth_history(db, patient_id, tooth)
    return ToothHistoryResponse(
        patient_id=patient_id,
        tooth=tooth,
        items=[ToothConditionRead.model_validate(r) for r in rows],
    )


@router.post(
    "/patients/{patient_id}/chart",
    response_model=ChartResponse,
    status_code=status.HTTP_201_CREATED,
)
def update_chart(
    patient_id: UUID,
    body: ChartUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> ChartResponse:
    """Mark one or more teeth, superseding whatever they said before.

    Partial: only the teeth listed change. Returns the full current chart, so
    the caller can render the result without a second request.
    """
    _patient_or_404(db, patient_id)

    try:
        mark_teeth(
            db,
            patient_id=patient_id,
            entries=body.entries,
            visit_id=body.visit_id,
            actor_id=staff.id,
        )
    except UnknownTooth as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{exc.args[0]}' is not an FDI tooth number.",
        ) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="update",
        entity="tooth_condition",
        entity_id=patient_id,
        details=jsonable_encoder(
            {
                "visit_id": body.visit_id,
                "teeth": [
                    {"tooth": e.tooth, "condition": e.condition} for e in body.entries
                ],
            }
        ),
    )
    db.commit()

    rows = current_chart(db, patient_id)
    return ChartResponse(
        patient_id=patient_id,
        items=[ToothConditionRead.model_validate(r) for r in rows],
        total=len(rows),
    )
