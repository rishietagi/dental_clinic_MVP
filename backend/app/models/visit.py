"""The visit model — one sitting, one row.

A visit is what actually happened on a given day: the complaint, the clinical
notes, and (via `procedure_performed`) the procedures done. Visits hang off a
`treatment`, which threads them together across weeks (BUILD_PLAN §3).

Foreign keys, and why each is nullable or not:

- `treatment_id` -> `treatment.id`, **NOT NULL**. This is the load-bearing
  decision of the model. Every visit belongs to a treatment, no exceptions —
  that is what makes the thread real. Single-visit work doesn't escape it: the
  visit API (4.3) auto-creates and auto-closes a treatment for a one-off
  cleaning, so the user never sees the concept. Allowing NULL here would let
  orphan visits accumulate and would silently break the "open treatments with no
  next appointment" report (4.8), the most valuable report in the app.

- `patient_id` -> `patient.id`, NOT NULL. Deliberately denormalised — it is
  reachable via the treatment, but nearly every clinical read is "this patient's
  visits", and carrying it directly avoids a join on the hottest query path.

- `appointment_id` -> `appointment.id`, **nullable**. Walk-ins happen (ERD §9);
  a visit with no appointment is normal, not an error.

- `dentist_id` -> `staff_user.id`, nullable. Matches `appointment.dentist_id`.

No `ondelete` on any of them: nothing in this app is ever hard-deleted (patients
archive, treatment items deactivate), so cascade behaviour would never fire.
Restrict-by-default is also the correct medico-legal answer — a treatment with
recorded visits must not be deletable.

No money here. Invoices are per-visit (ERD §9) and arrive in Phase 5.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Visit(Base):
    __tablename__ = "visit"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Denormalised from the treatment on purpose — see the module docstring.
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # NOT NULL: every visit hangs off a treatment. Indexed — "all sittings of
    # this treatment" is the query the treatment history screen runs (4.7).
    treatment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("treatment.id"), nullable=False, index=True
    )

    # Nullable: walk-ins have no appointment.
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("appointment.id"), nullable=True
    )

    # The PRIMARY dentist — who recorded / led the sitting. Nullable, mirroring
    # appointment.dentist_id.
    dentist_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_user.id"), nullable=True
    )

    # The CONSULTING dentist who actually did (part of) the work this sitting, if a
    # handoff happened. Always optional. The visit is the permanent clinical record,
    # so the handoff is captured HERE too, not just on the appointment.
    consulting_dentist_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_user.id"),
        nullable=True,
    )

    visit_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # What the patient came in with, in their words.
    complaint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What the dentist observed and did. One free-text field, not a structured
    # form — structured charting is out of scope.
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        return f"<Visit {self.visit_date} treatment={self.treatment_id}>"
