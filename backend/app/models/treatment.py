"""The treatment model — the thread that ties multiple visits together.

This is the heart of the clinical model (BUILD_PLAN §3). Dental work is often
multi-visit: an RCT is typically 2-4 sittings, and the dentist frequently does
NOT know the count upfront — it depends on infection severity, tooth anatomy,
and how the tooth responds. So a visit cannot be modelled as a standalone event;
it needs a thread to hang off:

    TREATMENT ("RCT on tooth 36", in_progress)
       |-- VISIT 1  (access opening, temp filling)
       |-- VISIT 2  (cleaning & shaping)
       `-- VISIT 3  (obturation + crown)  -> treatment closed

**A TREATMENT is NOT a treatment plan.** No cost estimate, no quote, no
acceptance tracking, no multi-option presentation — those are explicitly out of
scope. It answers three questions only: what is being done, to which tooth, is
it still ongoing. The absence of price columns here is deliberate; don't add them.

It exists so that the dentist opening a patient mid-course sees the prior
sittings' notes, and so the dashboard can flag **open treatments with no next
appointment booked** (4.8) — revenue walking out the door.

Simple cases stay simple: a one-visit cleaning is a treatment with exactly one
visit, auto-created and auto-closed by the visit API (4.3). The receptionist
never has to think about the word "treatment".

`status` is a plain Text column with no CHECK/enum — same choice as
`appointment.status`. The allowed values (`in_progress` / `completed`) and the
transitions between them are enforced in the API in step 4.5, which keeps the
schema flexible and avoids a second migration to loosen a constraint later.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Treatment(Base):
    __tablename__ = "treatment"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # A treatment always belongs to a patient. Indexed: the patient profile's
    # Treatments tab (4.7) reads by patient_id, as does the open-treatments
    # dashboard query (4.8).
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # Human-readable case name, e.g. "RCT tooth 36". Free text — the dentist's
    # own words are more useful here than a code list.
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # FDI tooth number as free text ("36"). Nullable: plenty of work isn't
    # tooth-specific (a scaling, a general check-up). This is NOT a charting
    # system — dental charting / odontogram is out of scope.
    tooth_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # in_progress / completed. No CHECK constraint — validated in the API (4.5).
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="in_progress"
    )

    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # Set when the treatment is closed; null while it's still open. The pair
    # (status, closed_at) is maintained together by the lifecycle API in 4.5.
    closed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Treatment {self.title!r} status={self.status}>"
