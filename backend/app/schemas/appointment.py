"""Appointment request/response schemas.

Booking (step 3.2). Note there is deliberately NO `status` field on create or
update: a new appointment always starts `booked`, and status transitions
(arrived / done / cancelled / no-show) are the step-3.5 workflow, not free-form
edits here.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    """Body for booking an appointment."""

    patient_id: UUID = Field(description="The patient being booked.")
    start_time: datetime = Field(description="Appointment start (timezone-aware).")
    duration_min: int = Field(default=30, ge=5, description="Slot length in minutes.")
    # Nullable: a slot may be booked before a dentist is assigned. Overlap is only
    # enforced once a dentist is set (see the booking service / DB constraint).
    dentist_id: UUID | None = None
    # Plain nullable column — no FK until Phase 4. A follow-up sets this; a first
    # booking leaves it None.
    treatment_id: UUID | None = None
    reason: str | None = None


class AppointmentUpdate(BaseModel):
    """Body for rescheduling / editing an appointment (PATCH).

    Every field optional. An omitted field is left unchanged; a field explicitly
    set to null is cleared. No `status` here — that's the 3.5 workflow.
    """

    start_time: datetime | None = None
    duration_min: int | None = Field(default=None, ge=5)
    dentist_id: UUID | None = None
    treatment_id: UUID | None = None
    reason: str | None = None


class AppointmentStatusUpdate(BaseModel):
    """Body for changing an appointment's status (POST /{id}/status).

    The `Literal` restricts the value to the five known statuses — an unknown
    status is a 422 here, distinct from the 409 the router raises for a *known but
    illegal* transition (e.g. done -> arrived). `no_show` is stored underscored.
    """

    status: Literal["booked", "arrived", "done", "cancelled", "no_show"]


class AppointmentRead(BaseModel):
    """Everything the API returns about a single appointment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    treatment_id: UUID | None
    dentist_id: UUID | None
    start_time: datetime
    duration_min: int
    status: str
    reason: str | None
    created_at: datetime
    updated_at: datetime


class AppointmentListItem(BaseModel):
    """A row in the day/list view.

    Like AppointmentRead but with the patient and dentist NAMES resolved (via a
    join in the list endpoint), because a calendar has to show who each
    appointment is for. `dentist_name` is None for an unassigned slot. Omits
    created_at/updated_at — a list row doesn't need them.
    """

    id: UUID
    patient_id: UUID
    patient_name: str
    dentist_id: UUID | None
    dentist_name: str | None
    treatment_id: UUID | None
    start_time: datetime
    duration_min: int
    status: str
    reason: str | None


class AppointmentListResponse(BaseModel):
    """A day's appointments plus the total count."""

    items: list[AppointmentListItem]
    total: int
