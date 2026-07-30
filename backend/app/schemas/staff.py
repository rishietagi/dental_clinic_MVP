"""Staff directory schemas (step 6.3; writes added 6.5; consultation fee 6.7).

A minimal summary for the dentist dropdowns (id + name + roles), plus `email` +
`active` for the Settings manage-staff list. `StaffCreate` registers a **name-only**
staff record (a dentist to assign/report on — NOT a login; the app is run under a
shared receptionist login). An explicit response model so we never leak columns.

`consultation_fee` (6.7) is what this dentist charges for a consultation. It is
`None` when unset — distinct from 0.00 — and the visit screen only offers a fee
that has actually been set.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StaffSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    roles: list[str]
    active: bool
    consultation_fee: Decimal | None = None


class StaffCreate(BaseModel):
    """Register a staff member (a dentist by default). NOT a login — just a record
    to assign on appointments/visits and attribute in reports."""

    name: str = Field(min_length=1, description="Full name, e.g. 'Dr. Meera Prabhu'.")
    email: str = Field(min_length=1, description="Contact email (info only; not a login). Unique.")
    roles: list[str] = Field(
        default_factory=lambda: ["dentist"],
        description="Roles for this record; defaults to ['dentist'].",
    )
    consultation_fee: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Consultation charge. Omit to leave unset.",
    )


class StaffUpdate(BaseModel):
    """Partial update (PATCH). Every field optional; omitted ones are unchanged.

    **Setting `consultation_fee` to null clears it** back to "not set", which is
    why the router distinguishes "field omitted" from "field sent as null" via
    `exclude_unset` rather than testing for None.

    `roles` and `active` are deliberately absent: activation has its own
    endpoints, and role changes are a bigger decision than a settings-page edit.
    """

    name: str | None = Field(default=None, min_length=1)
    consultation_fee: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )


class StaffListResponse(BaseModel):
    items: list[StaffSummary]
    total: int
