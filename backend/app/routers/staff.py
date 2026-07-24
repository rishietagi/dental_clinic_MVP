"""Staff directory + management (step 6.3 reads; 6.5 writes).

`GET /staff` powers the dentist dropdowns on the booking + visit screens; the writes
(6.5) let an admin register the clinic's dentists from Settings. These are
**name-only records**, NOT logins — the app runs under a shared receptionist login,
and a dentist here exists purely to be assigned on appointments/visits and
attributed in reports. So a created staff row gets a random local UUID (unlike the
seeded admin, whose id IS the Supabase Auth UUID).

- **Reads** — any active staff (names, not patient data). `?role=` filters;
  `?include_inactive=` shows deactivated rows for the manage list (default hides them).
- **Writes** — `require_role("admin")` (managing staff is Admin's job, BUILD_PLAN §2).
  Create → 409 on a duplicate email. Deactivate/activate are soft (never delete, so
  historical appointments/visits/reports keep resolving — the patient/treatment-item
  pattern). All audited.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_staff, require_role
from app.db import get_db
from app.models.staff_user import StaffUser
from app.schemas.staff import StaffCreate, StaffListResponse, StaffSummary
from app.services.audit import record_audit

router = APIRouter(prefix="/staff", tags=["staff"])

_DUPLICATE_DETAIL = "A staff member with that email already exists."


def _get_or_404(db: Session, staff_id: UUID) -> StaffUser:
    who = db.get(StaffUser, staff_id)
    if who is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found."
        )
    return who


@router.get("", response_model=StaffListResponse)
def list_staff(
    role: str | None = Query(
        default=None, description="Optional role filter, e.g. 'dentist'."
    ),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> StaffListResponse:
    """Staff by name, optionally filtered by role. Inactive hidden unless asked."""
    stmt = select(StaffUser)
    if not include_inactive:
        stmt = stmt.where(StaffUser.active.is_(True))
    if role is not None:
        stmt = stmt.where(StaffUser.roles.any(role))
    stmt = stmt.order_by(StaffUser.name)

    rows = db.scalars(stmt).all()
    return StaffListResponse(
        items=[StaffSummary.model_validate(s) for s in rows],
        total=len(rows),
    )


@router.post("", response_model=StaffSummary, status_code=status.HTTP_201_CREATED)
def create_staff(
    body: StaffCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> StaffUser:
    """Register a name-only staff record (a dentist by default). Admin-only."""
    who = StaffUser(
        id=uuid4(),  # a local key — NOT a Supabase login UUID
        name=body.name,
        email=body.email,
        roles=body.roles,
        active=True,
    )
    db.add(who)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="staff_user",
        entity_id=who.id,
        details=jsonable_encoder({"name": body.name, "email": body.email, "roles": body.roles}),
    )
    db.commit()
    db.refresh(who)
    return who


@router.post("/{staff_id}/deactivate", response_model=StaffSummary)
def deactivate_staff(
    staff_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> StaffUser:
    """Soft-deactivate a staff record (drops out of dropdowns; history still resolves)."""
    who = _get_or_404(db, staff_id)
    who.active = False
    record_audit(db, actor_id=staff.id, action="deactivate", entity="staff_user", entity_id=who.id)
    db.commit()
    db.refresh(who)
    return who


@router.post("/{staff_id}/activate", response_model=StaffSummary)
def activate_staff(
    staff_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(require_role("admin")),
) -> StaffUser:
    who = _get_or_404(db, staff_id)
    who.active = True
    record_audit(db, actor_id=staff.id, action="activate", entity="staff_user", entity_id=who.id)
    db.commit()
    db.refresh(who)
    return who
