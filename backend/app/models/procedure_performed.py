"""The procedure_performed model — which catalogue procedures a visit contained.

A join row between a `visit` and the `treatment_item` catalogue built in 4.1,
plus an optional tooth reference. One visit can contain several procedures (an
extraction and a scaling in the same sitting), hence a separate table rather
than a column on `visit`.

This is where 4.1's **"deactivate, never delete"** rule earns its keep: a
retired catalogue item must still resolve, or a visit recorded two years ago
becomes unreadable. That is why `treatment_item` has no DELETE route.

**No price column here — deliberately.** The ERD gives this table exactly four
columns, and invoicing is Phase 5. There is a real open question that 5.2 must
answer: should a procedure keep a snapshot of the price at the time it was
performed, so that re-reading an old visit doesn't silently show today's price?
That question belongs to the invoice model, not here — invoices are the record
of what was charged. Flagged in the LOG so 5.2 decides it consciously.

`tooth_ref` is per-procedure and distinct from `treatment.tooth_ref`: the
treatment is "RCT tooth 36" while a single sitting might also include a scaling
that isn't tooth-specific. Nullable for exactly that reason.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text

from app.models import Base


class ProcedurePerformed(Base):
    __tablename__ = "procedure_performed"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Indexed: reading a visit always fetches its procedures.
    visit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("visit.id"), nullable=False, index=True
    )

    # The catalogue link (4.1). Not null — a procedure without an item has no
    # name and no price, so it couldn't be invoiced or reported on.
    treatment_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("treatment_item.id"), nullable=False
    )

    # Optional per-procedure tooth, e.g. "36". See the module docstring.
    tooth_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ProcedurePerformed visit={self.visit_id} item={self.treatment_item_id}>"
