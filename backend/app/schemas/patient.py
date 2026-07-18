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
    medical_notes: str | None = None


class PatientRead(BaseModel):
    """Everything the API returns about a patient, including the computed age."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    phone: str | None
    date_of_birth: date | None
    age: int | None  # computed from date_of_birth by the model's @property
    gender: str | None
    medical_notes: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime
