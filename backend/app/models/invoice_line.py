"""The invoice_line model — one row per charged procedure on an invoice.

A line **snapshots** what was charged. `description` and `amount` are frozen at
generation time (5.2), copied from the `treatment_item` catalogue — they are NOT
read live from it. This is the deliberate answer to the price-snapshot question
raised in 4.2 and deferred to Phase 5: re-reading a two-year-old invoice must
show the price that was actually charged then, not today's catalogue price. An
item renamed or repriced afterwards leaves old invoices untouched.

Because the money and label are frozen on the line, `treatment_item_id` is kept
only as a **nullable** reporting link ("revenue by procedure"). Nullable so a line
still resolves even without a catalogue reference — the invoice reads correctly
from its own `description`/`amount` regardless. `treatment_item` is never
hard-deleted (it deactivates), so the link normally stays valid.

Money is `Numeric(10, 2)` / `Decimal`, never float (the 4.1 rule). A CHECK in the
migration rejects a negative amount.

No `ondelete`, no `relationship()` navigations — house style.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text

from app.models import Base


class InvoiceLine(Base):
    __tablename__ = "invoice_line"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Indexed: reading an invoice always fetches its lines.
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("invoice.id"), nullable=False, index=True
    )

    # Reporting link only ("revenue by procedure"). NULLABLE — the money/label is
    # already frozen on this row, so a line does not depend on the catalogue.
    treatment_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("treatment_item.id"), nullable=True
    )

    # FROZEN at generation (5.2). The label as charged, not read live.
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # FROZEN at generation (5.2). MONEY — Numeric, never float. CHECK: amount >= 0.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    def __repr__(self) -> str:
        return f"<InvoiceLine invoice={self.invoice_id} {self.description!r} {self.amount}>"
