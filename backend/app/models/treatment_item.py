"""The treatment_item model — the clinic's flat priced catalogue.

BUILD_PLAN §1 cut the "rate card" module but kept this: one small table of
`name + default_price` so an invoice line can pick something and get a price
without anyone re-typing it. It is NOT a rate card — no tiers, no codes.
Visits attach procedures to these items (4.3) and invoices price their lines
from them (5.2).

**`kind` (6.7)** splits the catalogue into `treatment` (dental procedures) and
`medicine` (dispensed at the chair). It is a *label on the same table*, not a
second table: medicines then ride the existing
`treatment_item -> procedure_performed -> invoice_line` pipeline for free,
including the 5.2 price snapshot and the procedure-mix report.

**The clinic's third charge, the consultation fee, is deliberately NOT a kind
here** — it is per-dentist, so it lives on `staff_user.consultation_fee` and
reaches an invoice as a custom line. See that model.

Two things this model establishes for the rest of the project:

- **Money is `Numeric`, NEVER float.** `default_price` is `Numeric(10, 2)`.
  Binary floating point cannot represent decimal currency exactly, and a rounding
  error in an invoice is a real-world bug. Python side: `Decimal`, never `float`.
- **Deactivate, never delete.** `active` hides an item from pickers while keeping
  the row readable, so historical visits/invoices that reference it still resolve.
  There is no DELETE route.

Names are unique **per kind** (6.7 replaced the bare unique on `name`):
duplicates within a kind would make "revenue by procedure" reporting
meaningless, which is the whole reason this table exists — but the same word can
legitimately name both a procedure and a medicine.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base

# The catalogue kinds. Kept as a module constant so the schema layer, the CHECK
# constraint and the tests all agree on one list.
ITEM_KINDS = ("treatment", "medicine")


class TreatmentItem(Base):
    __tablename__ = "treatment_item"

    __table_args__ = (
        # Unique PER KIND, not globally: "Consultation" may name both a procedure
        # and a medicine. Named by hand so a migration downgrade can drop it.
        UniqueConstraint("kind", "name", name="uq_treatment_item_kind_name"),
        CheckConstraint(
            "kind IN ('treatment', 'medicine')", name="ck_treatment_item_kind"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # 'treatment' (a dental procedure) or 'medicine'. The server_default is what
    # backfills the rows that existed before 6.7 — they are all procedures.
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="treatment", index=True
    )

    name: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # MONEY — Numeric, never Float. 10 digits total / 2 decimal places is ample
    # for clinic pricing in rupees (max 99,999,999.99).
    default_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Soft-deactivate. Never hard-delete: old invoices/visits must keep resolving.
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
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
        return (
            f"<TreatmentItem [{self.kind}] {self.name} {self.default_price}"
            f"{'' if self.active else ' [inactive]'}>"
        )
