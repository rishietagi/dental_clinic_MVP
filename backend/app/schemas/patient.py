"""Patient request/response schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    """Body for creating a patient. Only name is required."""

    name: str = Field(min_length=1, description="Patient full name.")
    phone: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    # Parent/guardian — "S/O" on the OPD card (6.10). Matters for paediatric
    # patients, who are the ones the clinic phones about appointments.
    guardian_name: str | None = None
    address: str | None = None
    # Next routine check-up (Phase 4 of the treatment workflow).
    recall_due: date | None = None
    medical_notes: str | None = None


class PatientUpdate(BaseModel):
    """Body for a partial update (PATCH). Every field optional.

    A field that is omitted is left unchanged; a field explicitly set to null is
    cleared. The router distinguishes the two via `exclude_unset`.
    """

    name: str | None = Field(default=None, min_length=1)
    phone: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    guardian_name: str | None = None
    address: str | None = None
    recall_due: date | None = None
    medical_notes: str | None = None


class PatientRead(BaseModel):
    """Everything the API returns about a single patient, including computed age."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone: str | None
    date_of_birth: date | None
    age: int | None  # computed from date_of_birth by the model's @property
    gender: str | None
    guardian_name: str | None = None
    address: str | None = None
    recall_due: date | None = None
    medical_notes: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class RecallDueItem(BaseModel):
    """A row of the "due for a check-up" dashboard list (6.10).

    Lighter than `PatientRead` and deliberately WITHOUT medical_notes — the same
    rule `PatientListItem` follows: sensitive notes are returned by the profile
    endpoint only, never in a bulk list.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone: str | None
    recall_due: date


class RecallDueResponse(BaseModel):
    items: list[RecallDueItem]
    total: int


class PatientListItem(BaseModel):
    """A row in the patient list/search results.

    Deliberately lighter than PatientRead — NO medical_notes. Sensitive notes are
    only returned by GET /patients/{id} (the profile), never in bulk list responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone: str | None
    date_of_birth: date | None
    age: int | None
    gender: str | None
    archived: bool


class PatientListResponse(BaseModel):
    """A page of patient list/search results plus the total match count."""

    items: list[PatientListItem]
    total: int
