"""Treatment read schemas (step 4.4).

Read-only for now. Treatments are **created** by `POST /visits` (4.3, the
auto-create rule) and their lifecycle — closing, reopening — is step 4.5, so
there is deliberately no Create/Update schema here yet.

`TreatmentSummary` in `schemas/visit.py` stays as-is: it's the trimmed shape
nested inside a visit response. This is the standalone read, which also carries
`patient_id` and the timestamps a list view wants.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TreatmentRead(BaseModel):
    """Everything the API returns about one treatment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    title: str
    tooth_ref: str | None
    status: str
    started_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TreatmentListResponse(BaseModel):
    """A patient's treatments plus the total count."""

    items: list[TreatmentRead]
    total: int
