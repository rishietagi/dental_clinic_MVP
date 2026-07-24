"""Staff directory schemas (step 6.3).

A minimal summary for the dentist dropdowns — id + name + roles. No email or other
profile detail (the dropdown only needs to label + identify), and an explicit
response model so we never leak columns.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StaffSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    roles: list[str]


class StaffListResponse(BaseModel):
    items: list[StaffSummary]
    total: int
