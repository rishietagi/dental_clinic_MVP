"""The payment model — one row per payment made against an invoice.

An invoice may be settled by **several** payments: a patient can part-pay a
sitting today and clear the balance next visit, so this is a separate table, not
an amount column on `invoice`. Summing an invoice's payments and comparing to its
`total` is what drives the `unpaid → partially_paid → paid` status and the
outstanding-balance figure — both of which arrive with payment capture (5.3).

Money is `Numeric(10, 2)` / `Decimal`, never float (the 4.1 rule). A CHECK in the
migration rejects a negative amount.

`mode` (cash / card / upi) is a plain Text column with no CHECK. The allowed
values get pinned in the Pydantic schema as a `Literal` when the payment API
arrives (5.3) — the same app-level-enum pattern as appointment status — so a new
payment method never needs a migration.

No `ondelete`, no `relationship()` navigations — house style.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Indexed: reading/settling an invoice sums its payments.
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("invoice.id"), nullable=False, index=True
    )

    # MONEY — Numeric, never float. CHECK: amount >= 0.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # cash / card / upi. No CHECK — pinned via a Pydantic Literal in the API (5.3).
    mode: Mapped[str] = mapped_column(Text, nullable=False)

    paid_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Payment invoice={self.invoice_id} {self.amount} {self.mode}>"
