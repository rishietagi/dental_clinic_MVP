"""The appointment model — one row per booked slot on the calendar.

An appointment is a scheduled visit: which patient, which dentist, when, for how
long, why, and where it is in its lifecycle (booked -> arrived -> done / cancelled
/ no-show). The status *workflow* (the allowed transitions) arrives in step 3.5;
this model only holds the column and its default.

Foreign keys — this is the schema's first table with real FKs:
- `patient_id` -> `patient.id`, NOT NULL. An appointment always belongs to a patient.
- `dentist_id` -> `staff_user.id`, nullable. A slot may be booked before a dentist
  is assigned (the clinic has effectively one dentist, so it's usually set).
- `treatment_id` -> `treatment.id`, nullable. A first-time booking has no
  treatment; a follow-up booked from a visit screen (4.6) carries the treatment
  it continues. This FK was **deferred from 3.1 to 4.2** because the `treatment`
  table didn't exist until Phase 4 — it is real now.

No `relationship()` navigations yet — plain FK columns until a step needs ORM
navigation (can be added later without a migration).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Appointment(Base):
    __tablename__ = "appointment"

    # Server-generated internal id. Never placed in a URL query string (hard rule).
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # A short human-readable id (shown as "A-1042"), added in 6.6 alongside lab
    # cases. The UUID above is unreadable and unsayable — staff need something they
    # can quote on the phone and match against a lab docket. Fed by a Postgres
    # sequence created in the migration (which also backfills existing rows).
    # `server_default` matters: it makes SQLAlchemy omit the column from INSERTs so
    # the sequence supplies the value, instead of sending an explicit NULL.
    number: Mapped[int] = mapped_column(
        Integer,
        server_default=text("nextval('appointment_number_seq')"),
        nullable=False,
        unique=True,
    )

    # Always belongs to a patient. First real FK in the schema.
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False
    )

    # Nullable: a first booking has no treatment; a follow-up does. The FK is
    # real as of 4.2 (deferred from 3.1 until `treatment` existed). No ondelete —
    # treatments are never hard-deleted, so cascade behaviour would never fire.
    treatment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("treatment.id"), nullable=True
    )

    # The PRIMARY dentist — who the appointment is booked under / who does the
    # initial check. Nullable: a slot may be booked before a dentist is assigned.
    dentist_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_user.id"), nullable=True
    )

    # The CONSULTING dentist (5.6-era handoff): a second dentist brought in for the
    # treatment when the primary hands it off. Always optional — most appointments
    # have one dentist; the handoff is the exception. Distinct FK to staff_user.
    consulting_dentist_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("staff_user.id"),
        nullable=True,
    )

    start_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    # Slot length in minutes. 30 is a sensible default; clinic settings tune the
    # default slot duration later (Phase 4).
    duration_min: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30"
    )

    # Lifecycle string: booked / arrived / done / cancelled / no-show. The
    # transition *workflow* + validation is step 3.5; here it's just the column
    # and its default. No CHECK/enum — kept flexible, validated in the API later.
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="booked"
    )

    # Free-text reason for the visit.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        return f"<Appointment {self.start_time} status={self.status}>"
