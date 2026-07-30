"""The lab_case model — one item of work sent out to a dental lab (step 6.6).

A crown/bridge/denture is made outside the clinic: an impression goes to a lab and
comes back days later to be fitted. Before this, that wait lived on paper and got
forgotten — the same "walks out the door" failure the follow-up report exists to
catch.

**The workflow decision this model encodes (and why):** when a sample is sent, the
APPOINTMENT still closes normally (`done`) — that sitting genuinely happened, and an
appointment is a *calendar slot*, so holding it open for five days would make the
calendar claim the dentist is busy on a past day. The wait is tracked HERE instead,
while the `treatment` stays `in_progress` (the app already threads multi-visit work),
so the patient keeps showing on the follow-up report. Nothing about the appointment
status machine changes.

**`number` is a short human-readable id** (rendered `L-231`). Every other entity in
this app is keyed by an unreadable UUID, which is fine for machines but useless for a
receptionist who has to quote a case to the lab on the phone and match it when the
box comes back. Fed by a Postgres sequence; unique; never reused.

Links, and why each is nullable or not:
- `patient_id` NOT NULL — a case is always for someone. Indexed (the profile lists them).
- `lab_id` NOT NULL — it went somewhere.
- `visit_id` / `appointment_id` **nullable** — usually set (the impression was taken at
  a sitting booked as an appointment), but a case can be raised standalone from the Lab
  tab, so neither is required.
- `created_by` nullable, mirroring `visit.dentist_id`.

**Lifecycle: `sent → received`, plus `cancelled`** — deliberately just two working
states (the clinic asked to keep it simple). No DB enum; the API enforces the
transitions, like appointment status. Because there is no "fitted" state, a received
case would otherwise disappear with nobody reminded to call the patient in — hence
**`follow_up_done`**, a plain dismiss flag behind the dashboard's "Back from lab" list.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Integer, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class LabCase(Base):
    __tablename__ = "lab_case"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # The short readable id (shown as "L-231"). Unique + never reused, so it can be
    # quoted to the lab. The value comes from a Postgres SEQUENCE created in the
    # migration — `server_default` is what makes SQLAlchemy OMIT the column from the
    # INSERT (rather than sending NULL) so the sequence default actually applies.
    number: Mapped[int] = mapped_column(
        Integer,
        server_default=text("nextval('lab_case_number_seq')"),
        nullable=False,
        unique=True,
    )

    # Always belongs to a patient. Indexed — the profile lists a patient's cases.
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # Which lab it went to.
    lab_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lab.id"), nullable=False
    )

    # The sitting / booking it came from. Nullable: a case can be raised standalone.
    visit_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("visit.id"), nullable=True
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("appointment.id"), nullable=True
    )

    # What was sent (crown / bridge / denture_full / ... / other). Free-text column,
    # pinned to a set by a Pydantic Literal in the API — the app-level-enum pattern.
    sample_type: Mapped[str] = mapped_column(Text, nullable=False)

    # FDI tooth as free text ("36"). Natural for a crown; not every case has one.
    tooth_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plain DATEs, not timestamps: "sent on the 24th" is a calendar fact the
    # receptionist reads off a docket — no clock time, so no timezone ambiguity.
    sent_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # sent / received / cancelled. No CHECK — transitions enforced in the API.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="sent")

    # Dismiss flag for the "Back from lab — call the patient in" dashboard nudge.
    # Not a status: the receptionist ticks it off, she doesn't reason about a state.
    follow_up_done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_user.id"), nullable=True
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
        return f"<LabCase L-{self.number} {self.sample_type} status={self.status}>"
