"""Lab vendor endpoints (step 6.6) — the list of labs the clinic sends work to.

Mirrors the treatment catalogue (4.1) exactly, for the same reasons:
- **Reads** — any active staff (the receptionist picks a lab when sending a sample).
- **Writes** — `require_role("admin")` (curating the vendor list is an Admin job).
- **Deactivate, never delete** — a retired lab must still resolve, or an old lab case
  becomes unreadable. There is no DELETE route.

`name` is unique, so a duplicate returns a friendly **409** rather than a raw
constraint error.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.lab import Lab
from app.models.staff_user import StaffUser
from app.schemas.lab import LabCreate, LabListResponse, LabRead
from app.services.audit import record_audit

router = APIRouter(prefix="/labs", tags=["labs"])

_DUPLICATE_DETAIL = "A lab with that name already exists."


def _get_or_404(db: Session, lab_id: UUID) -> Lab:
    lab = db.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab not found.")
    return lab


@router.get("", response_model=LabListResponse)
def list_labs(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> LabListResponse:
    """The labs available in the picker. Inactive hidden unless asked for."""
    stmt = select(Lab)
    if not include_inactive:
        stmt = stmt.where(Lab.active.is_(True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Lab.name)).all()
    return LabListResponse(items=[LabRead.model_validate(r) for r in rows], total=total)


@router.post("", response_model=LabRead, status_code=status.HTTP_201_CREATED)
def create_lab(
    body: LabCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> Lab:
    lab = Lab(**body.model_dump())
    db.add(lab)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="lab",
        entity_id=lab.id,
        details=jsonable_encoder(body.model_dump()),
    )
    db.commit()
    db.refresh(lab)
    return lab


@router.post("/{lab_id}/deactivate", response_model=LabRead)
def deactivate_lab(
    lab_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> Lab:
    """Retire a lab: it leaves the picker but old cases still resolve."""
    lab = _get_or_404(db, lab_id)
    lab.active = False
    record_audit(db, actor_id=staff.id, action="deactivate", entity="lab", entity_id=lab.id)
    db.commit()
    db.refresh(lab)
    return lab


@router.post("/{lab_id}/activate", response_model=LabRead)
def activate_lab(
    lab_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> Lab:
    lab = _get_or_404(db, lab_id)
    lab.active = True
    record_audit(db, actor_id=staff.id, action="activate", entity="lab", entity_id=lab.id)
    db.commit()
    db.refresh(lab)
    return lab
