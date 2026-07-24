"""Practice-report endpoints (step 6.1).

One read, `GET /reports`, bundling the three reports the owner's screen shows —
revenue trend, procedure mix, no-show rate. **`require_role("dentist","admin")`**:
reports are the owner's/dentist's view of the practice (BUILD_PLAN §2), not the
receptionist's — the same split the "Reports" nav item already assumes. Read-only,
unaudited (like the other read endpoints).

The aggregates live in `services/reports.py`; this router just wires the query
params and the response.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models.staff_user import StaffUser
from app.schemas.report import ReportsResponse
from app.services.reports import (
    no_show_rate,
    procedure_mix,
    revenue_by_dentist,
    revenue_trend,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ReportsResponse)
def get_reports(
    months: int = Query(default=6, ge=1, le=24),
    days: int = Query(default=30, ge=1, le=365),
    dentist_id: UUID | None = Query(
        default=None, description="Optional: narrow the trend/mix/no-show to one dentist."
    ),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("dentist", "admin")),
) -> ReportsResponse:
    """Revenue trend (last `months`), procedure mix (last `months`), no-show rate
    (last `days`) — all clinic-timezone-bucketed — plus a per-dentist breakdown.

    `dentist_id` narrows the three trend/mix/no-show reports to one dentist; the
    `by_dentist` breakdown is always the full comparison (unfiltered)."""
    return ReportsResponse(
        revenue_trend=revenue_trend(db, months=months, dentist_id=dentist_id),
        procedure_mix=procedure_mix(db, months=months, dentist_id=dentist_id),
        no_show=no_show_rate(db, days=days, dentist_id=dentist_id),
        by_dentist=revenue_by_dentist(db, months=months),
    )
