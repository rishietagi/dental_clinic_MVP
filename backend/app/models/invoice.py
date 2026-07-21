"""The invoice model — one invoice per visit (ERD §9).

A patient pays **per sitting**, not per treatment: each visit produces one
invoice. That is the load-bearing decision here, and the DB enforces it — a
UNIQUE constraint on `visit_id` makes a second invoice for the same visit
impossible, so the "one invoice per visit" rule can't be violated by a racing
second PC (the same instinct as the appointment overlap constraint).

`patient_id` is carried directly (reachable via the visit, but denormalised)
because "this patient's billing history" is a hot read on the profile — the same
reason `visit.patient_id` is denormalised from the treatment.

Money is `Numeric(10, 2)` / `Decimal`, NEVER float (the 4.1 rule — invoices are
the reason that rule exists). `subtotal` is the sum of the lines, `discount` is
applied to the whole invoice, `total = subtotal - discount`. The values are
maintained together by the invoice-generation service in 5.2; the migration adds
CHECK constraints so the DB itself rejects negative money or a discount larger
than the subtotal.

`status` is a plain Text column with no CHECK/enum — the same choice as
`appointment.status` and `treatment.status`. The allowed values
(`unpaid` / `partially_paid` / `paid`) and the transitions between them are
enforced in the service layer when payment capture arrives (5.3), which keeps the
schema flexible and avoids a migration to loosen a constraint later.

No `ondelete` and no `relationship()` navigations — house style. Nothing in this
app is hard-deleted, and every query is written explicitly.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Invoice(Base):
    __tablename__ = "invoice"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Denormalised from the visit — "this patient's billing history" is the hot read.
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), nullable=False, index=True
    )

    # One invoice per visit. UNIQUE is the real guarantee (ERD §9): a second
    # invoice for the same visit is impossible at the DB, not just in the service.
    visit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("visit.id"), nullable=False, unique=True
    )

    # MONEY — Numeric, never float. Maintained together by the 5.2 generation
    # service; non-negativity + discount<=subtotal enforced by CHECKs (migration).
    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0"
    )
    discount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0"
    )
    total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, server_default="0"
    )

    # unpaid / partially_paid / paid. No CHECK — validated in the API (5.3).
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="unpaid"
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
        return f"<Invoice visit={self.visit_id} total={self.total} status={self.status}>"
