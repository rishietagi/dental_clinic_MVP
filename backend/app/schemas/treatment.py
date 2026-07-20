"""Treatment read schemas (steps 4.4, 4.8).

Read-only. Treatments are **created** by `POST /visits` (4.3, the auto-create
rule) and their lifecycle — closing, reopening — is step 4.5, so there is
deliberately no Create/Update schema here.

`TreatmentSummary` in `schemas/visit.py` stays as-is: it's the trimmed shape
nested inside a visit response. `TreatmentRead` is the standalone read.
`TreatmentNeedsFollowUp` (4.8) is the dashboard row for the "open treatments with
no next appointment" report — it carries the patient's name and last-visit date
so the dashboard can render an actionable, patient-linked row.
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


class TreatmentNeedsFollowUp(BaseModel):
    """A dashboard row: an open treatment with no upcoming appointment (4.8)."""

    id: UUID
    patient_id: UUID
    patient_name: str
    title: str
    tooth_ref: str | None
    started_at: datetime
    # None when the treatment has no recorded visits yet (created but never
    # recorded against) — still a valid thing to flag.
    last_visit_date: datetime | None


class NeedsFollowUpResponse(BaseModel):
    """The clinic-wide follow-up report plus a total count."""

    items: list[TreatmentNeedsFollowUp]
    total: int
