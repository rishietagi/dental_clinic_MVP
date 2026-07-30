"""Lab management schemas (step 6.6) — vendors and lab cases.

`SampleType` is a `Literal`, so an unknown sample type is a 422 at the schema
boundary rather than free text drifting into the data — the app-level-enum pattern
used for appointment status and payment mode. "other" pairs with `notes` for the
unusual case.

Dates are plain `date`, not datetimes: "sent on the 24th" is a calendar fact read off
a docket, with no clock time and so no timezone ambiguity.

Reads carry the resolved `patient_name` / `lab_name` / `appointment_number` (joined in
the router) because a lab list that shows only UUIDs is unusable at the front desk.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The lab work this clinic actually sends out. Kept in sync with the frontend picker.
SampleType = Literal[
    "crown",
    "bridge",
    "denture_full",
    "denture_partial",
    "inlay_onlay",
    "veneer",
    "orthodontic",
    "study_model",
    "other",
]

LabCaseStatus = Literal["sent", "received", "cancelled"]


# --- labs (the vendor list) --------------------------------------------------

class LabCreate(BaseModel):
    """Register a lab the clinic sends work to."""

    name: str = Field(min_length=1, description="Lab name, e.g. 'Sri Dental Lab'.")
    phone: str | None = Field(default=None, description="Who to call when a case is late.")
    address: str | None = None


class LabRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone: str | None
    address: str | None
    active: bool
    created_at: datetime


class LabListResponse(BaseModel):
    items: list[LabRead]
    total: int


# --- lab cases ---------------------------------------------------------------

class LabCaseCreate(BaseModel):
    """Send a sample to a lab.

    `visit_id` / `appointment_id` are optional: usually set (the impression was taken
    at a booked sitting), but a case can be raised standalone from the Lab tab.
    """

    patient_id: UUID
    lab_id: UUID
    sample_type: SampleType
    sent_date: date
    expected_date: date | None = Field(
        default=None, description="When the lab expects to have it back."
    )
    visit_id: UUID | None = None
    appointment_id: UUID | None = None
    tooth_ref: str | None = Field(default=None, description="FDI tooth, e.g. '36'.")
    notes: str | None = None

    @model_validator(mode="after")
    def _dates_sane(self) -> "LabCaseCreate":
        """A case can't be expected back before it was sent (the DB CHECK too)."""
        if self.expected_date is not None and self.expected_date < self.sent_date:
            raise ValueError("The expected date can't be before the sent date.")
        return self


class LabCaseReceive(BaseModel):
    """Mark a case as back from the lab. Defaults to today when omitted."""

    received_date: date | None = None


class LabCaseFollowUp(BaseModel):
    """Tick off (or re-open) the 'call the patient in' nudge."""

    done: bool = True


class LabCaseRead(BaseModel):
    """One lab case, with the names/numbers a human needs to read it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int  # rendered "L-231" by the frontend
    patient_id: UUID
    patient_name: str
    lab_id: UUID
    lab_name: str
    visit_id: UUID | None
    appointment_id: UUID | None
    appointment_number: int | None  # rendered "A-1042"
    sample_type: str
    tooth_ref: str | None
    sent_date: date
    expected_date: date | None
    received_date: date | None
    status: str
    follow_up_done: bool
    notes: str | None
    created_at: datetime


class LabCaseListResponse(BaseModel):
    items: list[LabCaseRead]
    total: int


class LabCaseSummary(BaseModel):
    """A light shape for showing "this visit sent something to the lab"."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int
    sample_type: str
    status: str
    sent_date: date
    expected_date: date | None


class LabDashboard(BaseModel):
    """The dashboard's lab view.

    `overdue` — still at the lab, expected date has passed (the case someone forgot
    to chase). `due_soon` — still at the lab, due within the window. `back_from_lab` —
    received but the patient hasn't been called in yet (`follow_up_done` false).
    """

    overdue: list[LabCaseRead]
    due_soon: list[LabCaseRead]
    back_from_lab: list[LabCaseRead]
