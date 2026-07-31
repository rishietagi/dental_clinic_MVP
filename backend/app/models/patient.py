"""The patient model — one row per patient of the clinic.

Real, sensitive health data kept for years. Two rules shape this table:
- **Soft-delete only** via the `archived` flag. Patients are NEVER hard-deleted
  (medico-legal retention, ≥3 years / ideally 7).
- **`medical_notes`** is one free-text field. When non-empty it renders as a
  banner on the profile (later steps). No structured allergy tables.

Design note: we store `date_of_birth`, not an `age` integer. A stored age goes
stale the moment it's recorded; DOB is always correct and age is computed on read
(see the `age` property). Deviation from the ERD's `int age`, on purpose.
"""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Patient(Base):
    __tablename__ = "patient"

    # Server-generated internal id. Never placed in a URL query string (hard rule).
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)

    # String, never int — leading zeros, +91, formatting. Nullable: not every
    # walk-in leaves a number.
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Age is computed from this (see `age`). Nullable when the DOB is unknown.
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    gender: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Parent / guardian ("S/O" on the OPD card, 6.10). Nullable — only paediatric
    # and dependent patients need one, but for those it is the person who
    # consents and who the clinic actually phones.
    guardian_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free-text address (6.10). One field, not split into lines/city/pin: Indian
    # addresses don't decompose cleanly and nothing here needs to query them.
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When this patient is next due a routine check-up (Phase 4 of the treatment
    # workflow — "every 3 to 6 months"). A plain date, not an appointment: a
    # recall is a reminder that they SHOULD be booked, which is exactly the
    # revenue the clinic currently loses track of. The dashboard lists whoever
    # is due; booking them creates a normal appointment.
    recall_due: Mapped[date | None] = mapped_column(Date, nullable=True)

    # The one free-text medical field; renders as a banner if non-empty.
    medical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft-delete flag. NEVER hard-delete a patient row.
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
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

    @property
    def age(self) -> int | None:
        """Age in whole years, computed from date_of_birth. None if DOB unknown."""
        if self.date_of_birth is None:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        # Subtract one if this year's birthday hasn't happened yet.
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    def __repr__(self) -> str:
        return f"<Patient {self.name}{' [archived]' if self.archived else ''}>"
