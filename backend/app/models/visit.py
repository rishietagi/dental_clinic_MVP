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

from sqlalchemy import CheckConstraint, ForeignKey, Integer, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base

# What can be ordered under "Inv:" on the OPD card. App-level vocabulary,
# mirrored by a Pydantic Literal — no DB enum (the house rule since 3.5).
INVESTIGATIONS = ("iopa", "opg_conventional", "opg_digital", "other")


class Visit(Base):
    __tablename__ = "visit"

    __table_args__ = (
        # Blood pressure, when recorded, must be plausible. Bounds are wide on
        # purpose — this is a typo guard, not a clinical judgement.
        CheckConstraint(
            "bp_systolic IS NULL OR (bp_systolic BETWEEN 50 AND 300)",
            name="ck_visit_bp_systolic_range",
        ),
        CheckConstraint(
            "bp_diastolic IS NULL OR (bp_diastolic BETWEEN 30 AND 200)",
            name="ck_visit_bp_diastolic_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Human-readable OPD number, shown as "V-1042" (6.10). Same mechanism as
    # appointment.number / lab_case.number from 6.6 — a Postgres sequence.
    #
    # CRITICAL: `server_default` must be set here or SQLAlchemy sends an explicit
    # NULL on insert instead of letting the sequence fill it, and EVERY insert
    # fails. That bug bit in 6.6; don't reintroduce it.
    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("nextval('visit_number_seq')"),
        unique=True,
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

    # --- the OPD card, field for field (6.10) -----------------------------
    #
    # These mirror the paper out-patient card the clinic already uses, in its
    # order, so the dentist can transcribe top-to-bottom without hunting. All
    # nullable: a routine cleaning fills almost none of them, and a form that
    # demands seven findings for a scaling is a form people stop using.
    #
    # Free text rather than code lists on purpose. Dentistry has no small enough
    # vocabulary for these, and the clinic's own shorthand ("NAD", "NRMH") is
    # more useful to them than an enum we invented.

    # What the patient came in with, in their words.
    complaint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Medical / dental / drug / allergy history AS AT THIS SITTING. Distinct
    # from `patient.medical_notes`, which is the standing record: this captures
    # what was asked and answered today (often just "NRMH").
    history_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Vitals. BP is the one that matters chairside — before an extraction or LA.
    bp_systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bp_diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Examination, in the card's own order.
    habits: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_oral: Mapped[str | None] = mapped_column(Text, nullable=True)
    intra_oral: Mapped[str | None] = mapped_column(Text, nullable=True)
    soft_tissues: Mapped[str | None] = mapped_column(Text, nullable=True)
    hard_tissue: Mapped[str | None] = mapped_column(Text, nullable=True)
    occlusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_teeth: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_findings: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Investigations ordered. A Postgres text ARRAY, not a comma-joined string —
    # the same choice `staff_user.roles` makes, and it keeps "how many OPGs this
    # month" a real query instead of a LIKE.
    investigations: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    investigation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Diagnosis — the clinical conclusion, and the biggest gap this step closes:
    # before 6.10 the record had nowhere to say what was actually wrong.
    provisional_diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    differential_diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Referral out ("REF/Dept No" on the card).
    referred_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What the dentist observed and did, in prose. Kept alongside the structured
    # fields above — dentists write both, and forcing everything into boxes
    # loses the sentence that explains the case.
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
