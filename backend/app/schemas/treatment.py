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
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TreatmentRead(BaseModel):
    """Everything the API returns about one treatment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    title: str
    tooth_ref: str | None
    status: str
    # Which of the four treatment phases this case has reached (6.10). Null
    # until someone sets it — plenty of work never needs phasing.
    phase: int | None = None
    started_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TreatmentPhaseUpdate(BaseModel):
    """Body for `POST /treatments/{id}/phase` (6.10).

    An action endpoint rather than a bare PATCH: the treatments router
    deliberately exposes no general replace route (a test pins that
    `PATCH /treatments/{id}` stays 405), because treatments are born from
    `POST /visits` and only change through named lifecycle actions —
    close, reopen, and now phase.

    `None` clears the phase; 1-4 set it. Anything else is a 422.
    """

    phase: Literal[1, 2, 3, 4] | None = Field(
        default=None, description="1-4, or null to clear."
    )


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
