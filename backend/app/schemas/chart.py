"""Dental chart schemas (step 6.11).

`condition` is a `Literal`, so an unknown one is a 422 before it reaches the
column — the same app-level-vocabulary choice as appointment status (3.5),
payment mode (5.3) and investigations (6.10). No DB enum, so the list can grow
without a migration.

`condition: None` is meaningful, not missing: it means "this tooth is sound
again", which supersedes whatever was there without recording anything new.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ToothConditionName = Literal[
    "caries",
    "filled",
    "crown",
    "root_canal",
    "missing",
    "implant",
    "bridge",
    "impacted",
    "fractured",
    "mobile",
]


class ToothMark(BaseModel):
    """One tooth's finding. `condition=None` clears it back to sound."""

    tooth: str = Field(description="FDI number — 11-48 permanent, 51-85 deciduous.")
    condition: ToothConditionName | None = None
    surfaces: str | None = Field(
        default=None, description="Which surfaces, when it matters: 'MOD', 'O', 'B'."
    )
    note: str | None = None


class ChartUpdate(BaseModel):
    """Mark one or more teeth.

    Partial by design: only the teeth listed are touched. A dentist marks the
    two teeth they examined, and clearing the other thirty because they went
    unmentioned would be data loss disguised as a save.
    """

    entries: list[ToothMark] = Field(min_length=1)
    visit_id: UUID | None = Field(
        default=None, description="The sitting these findings came from, if any."
    )


class ToothConditionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tooth: str
    condition: str
    surfaces: str | None
    note: str | None
    recorded_visit_id: UUID | None
    recorded_at: datetime
    superseded_at: datetime | None


class ChartResponse(BaseModel):
    """The patient's current chart.

    A tooth with no entry is sound — the absence of a row is the statement, so a
    new patient's chart is empty rather than 32 rows of "fine".
    """

    patient_id: UUID
    items: list[ToothConditionRead]
    total: int


class ToothHistoryResponse(BaseModel):
    """Everything ever recorded for one tooth, oldest first."""

    patient_id: UUID
    tooth: str
    items: list[ToothConditionRead]
