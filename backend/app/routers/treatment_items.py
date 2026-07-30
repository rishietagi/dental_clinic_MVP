"""Treatment catalogue endpoints (step 4.1).

**The first role-split resource.** Everything before this guarded every route with
`get_current_staff` (any active staff). Here the split matters (BUILD_PLAN §2):

- **Reads** — any active staff. The dentist and receptionist need the catalogue to
  pick procedures when recording visits (4.3) and building invoices (5.2).
- **Writes** — `require_role("admin")`. Editing the treatment list is an Admin
  responsibility. Enforced HERE, on the API: the frontend also hides the controls
  from non-admins, but a hidden button is not security.

Items are **deactivated, never deleted**, so historical visits/invoices that point
at an item keep resolving. There is no DELETE route.

`name` is unique **within a kind** (6.7) — a duplicate returns 409 rather than a
raw constraint error. Across kinds the same name is fine: "Consultation" may be
both a procedure and a medicine.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.staff_user import StaffUser
from app.models.treatment_item import TreatmentItem
from app.schemas.treatment_item import (
    ItemKind,
    TreatmentItemCreate,
    TreatmentItemListResponse,
    TreatmentItemRead,
    TreatmentItemUpdate,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/treatment-items", tags=["treatment-items"])

_DUPLICATE_DETAIL = "An item of that kind with that name already exists."

# The composite unique from migration 36f29754ba8d. 6.7 replaced the old
# single-column `ix_treatment_item_name`; matching on the stale name here would
# have let a duplicate surface as a raw 500 instead of a friendly 409.
_DUPLICATE_CONSTRAINT = "uq_treatment_item_kind_name"


def _get_or_404(db: Session, item_id: UUID) -> TreatmentItem:
    item = db.get(TreatmentItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Treatment item not found."
        )
    return item


def _commit_or_duplicate(db: Session) -> None:
    """Commit, turning a unique-name violation into a friendly 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _DUPLICATE_CONSTRAINT in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL
            ) from exc
        raise


@router.get("", response_model=TreatmentItemListResponse)
def list_treatment_items(
    include_inactive: bool = Query(default=False),
    kind: ItemKind | None = Query(
        default=None, description="Filter to one kind. Omit for all kinds."
    ),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> TreatmentItemListResponse:
    """The catalogue, ordered by kind then name. Any active staff may read it.

    Inactive (retired) items are hidden unless include_inactive=true — pickers
    want only live items, but Settings needs to show and restore the retired ones.

    `kind` is **optional and unfiltered by default** so every caller written
    before 6.7 keeps seeing the whole catalogue; the Pricing tabs and the visit
    form's separate sections pass it to get one kind at a time.
    """
    base = select(TreatmentItem)
    if not include_inactive:
        base = base.where(TreatmentItem.active.is_(True))
    if kind is not None:
        base = base.where(TreatmentItem.kind == kind)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(TreatmentItem.kind, TreatmentItem.name)).all()

    return TreatmentItemListResponse(
        items=[TreatmentItemRead.model_validate(i) for i in rows],
        total=total,
    )


@router.get("/{item_id}", response_model=TreatmentItemRead)
def get_treatment_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> TreatmentItem:
    # Inactive items are still returned — they're retired, not deleted.
    return _get_or_404(db, item_id)


@router.post("", response_model=TreatmentItemRead, status_code=status.HTTP_201_CREATED)
def create_treatment_item(
    body: TreatmentItemCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> TreatmentItem:
    item = TreatmentItem(**body.model_dump())
    db.add(item)
    try:
        db.flush()  # assign the id (and surface a duplicate) before auditing
    except IntegrityError as exc:
        db.rollback()
        if _DUPLICATE_CONSTRAINT in str(exc.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL
            ) from exc
        raise

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="treatment_item",
        entity_id=item.id,
        details=jsonable_encoder(body.model_dump()),
    )
    _commit_or_duplicate(db)
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=TreatmentItemRead)
def update_treatment_item(
    item_id: UUID,
    body: TreatmentItemUpdate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> TreatmentItem:
    item = _get_or_404(db, item_id)

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return item

    for field, value in changes.items():
        setattr(item, field, value)

    record_audit(
        db,
        actor_id=staff.id,
        action="update",
        entity="treatment_item",
        entity_id=item.id,
        details=jsonable_encoder(changes),
    )
    _commit_or_duplicate(db)
    db.refresh(item)
    return item


def _set_active(item_id: UUID, active: bool, db: Session, staff: StaffUser) -> TreatmentItem:
    item = _get_or_404(db, item_id)
    item.active = active
    record_audit(
        db,
        actor_id=staff.id,
        action="activate" if active else "deactivate",
        entity="treatment_item",
        entity_id=item.id,
    )
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/deactivate", response_model=TreatmentItemRead)
def deactivate_treatment_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> TreatmentItem:
    """Retire an item: hidden from pickers, but the row stays so past visits and
    invoices that reference it still resolve. Never a hard delete."""
    return _set_active(item_id, False, db, staff)


@router.post("/{item_id}/activate", response_model=TreatmentItemRead)
def activate_treatment_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> TreatmentItem:
    return _set_active(item_id, True, db, staff)
