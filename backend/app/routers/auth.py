"""Auth-related endpoints: who am I, and a role-guard demonstration."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_staff, require_role
from app.models.staff_user import StaffUser

router = APIRouter()


class StaffMe(BaseModel):
    """What the frontend needs to know about the signed-in staff member.

    An explicit response model so we never accidentally leak columns — only
    these fields are serialized.
    """

    id: UUID
    email: str
    name: str
    roles: list[str]
    active: bool

    model_config = {"from_attributes": True}


@router.get("/me", response_model=StaffMe)
def read_me(staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
    """The current staff member and their roles. Any authenticated staff user."""
    return staff


@router.get("/admin/ping")
def admin_ping(staff: StaffUser = Depends(require_role("admin"))) -> dict[str, bool]:
    """Admin-only. Exists to prove role enforcement (403 for non-admins)."""
    return {"ok": True}
