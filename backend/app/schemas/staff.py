"""Staff directory schemas (step 6.3; writes added 6.5).

A minimal summary for the dentist dropdowns (id + name + roles), plus `email` +
`active` for the Settings manage-staff list. `StaffCreate` registers a **name-only**
staff record (a dentist to assign/report on — NOT a login; the app is run under a
shared receptionist login). An explicit response model so we never leak columns.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StaffSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    roles: list[str]
    active: bool


class StaffCreate(BaseModel):
    """Register a staff member (a dentist by default). NOT a login — just a record
    to assign on appointments/visits and attribute in reports."""

    name: str = Field(min_length=1, description="Full name, e.g. 'Dr. Meera Prabhu'.")
    email: str = Field(min_length=1, description="Contact email (info only; not a login). Unique.")
    roles: list[str] = Field(
        default_factory=lambda: ["dentist"],
        description="Roles for this record; defaults to ['dentist'].",
    )


class StaffListResponse(BaseModel):
    items: list[StaffSummary]
    total: int
