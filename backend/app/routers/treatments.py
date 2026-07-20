"""Treatment read endpoints (step 4.4).

**Read-only, deliberately.** Treatments are created by `POST /visits` — the
auto-create rule from 4.3 — and closing/reopening one is the 4.5 lifecycle step.
Adding write routes here would build ahead of the roadmap.

This exists because the visit record screen (4.4) has to offer the dentist the
patient's *open* treatments to continue ("sitting 2 of the RCT") versus starting
new work. 4.5, 4.7 (treatment history) and 4.8 (open treatments with no next
appointment) all need the same read.

Reads are open to any active staff and are not audited — same convention as the
patient and appointment reads.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.schemas.treatment import TreatmentListResponse, TreatmentRead

router = APIRouter(prefix="/treatments", tags=["treatments"])


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
    treatment = db.get(Treatment, treatment_id)
    if treatment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Treatment not found."
        )
    return treatment
