"""The tooth_condition model — the patient's dental chart (step 6.11).

**A deliberate scope reversal.** `CLAUDE.md` listed dental charting / odontogram
as out of scope through Phase 6. The clinic owner asked for it explicitly after
seeing the OPD card work, so it is built on purpose — like patient file uploads
(5.6) and lab tracking (6.6) before it. Don't "correct" it back out.

**Append-only, never updated in place.** Marking tooth 16 as *filled* when it was
*caries* does not overwrite the old row: it stamps `superseded_at` on it and
inserts a new one. So

    current chart  = rows WHERE superseded_at IS NULL
    tooth history  = every row for that tooth, oldest first

That is the same instinct as everything else here — patients archive, catalogue
items deactivate, the audit log only ever appends — and it is the right
medico-legal answer. A dental chart is evidence: "what did this mouth look like
in March, before the treatment" has to stay answerable, and a mutable chart
silently loses that the moment anyone corrects a tooth.

**FDI notation, permanent AND deciduous.** Quadrants 1-4 are the permanent teeth
(11-48) and 5-8 the deciduous ones (51-85). Both are needed: the clinic treats
children, and a nine-year-old in mixed dentition has teeth from both sets in the
mouth at once.

Conditions are **app-level, no DB enum** (the house rule since 3.5) — validated
by a Pydantic `Literal` so the vocabulary can grow without a migration. `sound`
is deliberately not a value: a healthy tooth is the *absence* of a row, so a new
patient starts with an empty chart rather than 32 rows saying "fine".
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base

# Permanent teeth: quadrants 1-4, positions 1-8 (11-18, 21-28, 31-38, 41-48).
PERMANENT_TEETH = tuple(
    f"{quadrant}{position}" for quadrant in (1, 2, 3, 4) for position in range(1, 9)
)
# Deciduous teeth: quadrants 5-8, positions 1-5 (51-55, 61-65, 71-75, 81-85).
DECIDUOUS_TEETH = tuple(
    f"{quadrant}{position}" for quadrant in (5, 6, 7, 8) for position in range(1, 6)
)
ALL_TEETH = PERMANENT_TEETH + DECIDUOUS_TEETH

# What a general dentist actually marks. Kept short on purpose — a list nobody
# can hold in their head gets used inconsistently, which defeats the chart.
TOOTH_CONDITIONS = (
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
)


class ToothCondition(Base):
    __tablename__ = "tooth_condition"

    __table_args__ = (
        # The chart read: "this patient's current teeth". Partial index — only
        # current rows are ever queried this way, and superseded history grows
        # without end, so indexing it would be wasted space.
        Index(
            "ix_tooth_condition_current",
            "patient_id",
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # FDI number as text ("16", "55"). Text not int: leading digits are
    # positional, not arithmetic — nothing sensible comes of adding two teeth.
    tooth: Mapped[str] = mapped_column(Text, nullable=False)

    condition: Mapped[str] = mapped_column(Text, nullable=False)

    # Which surfaces, when it matters: "MOD", "O", "B". Free text, nullable —
    # a missing tooth has no surfaces and an implant needs none.
    surfaces: Mapped[str | None] = mapped_column(Text, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The sitting this was found/done at, when it came from one. Nullable: a
    # chart can also be filled in from an old paper record with no visit behind it.
    recorded_visit_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("visit.id"), nullable=True
    )
    recorded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("staff_user.id"), nullable=True
    )

    recorded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # NULL = this is the tooth's current state. Non-null = it was replaced by a
    # later finding, and this row is history.
    superseded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        state = "" if self.superseded_at is None else " [superseded]"
        return f"<ToothCondition {self.tooth} {self.condition}{state}>"
