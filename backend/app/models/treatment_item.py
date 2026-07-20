"""The treatment_item model — the clinic's flat treatment/procedure catalogue.

BUILD_PLAN §1 cut the "rate card" module but kept this: one small table of
`name + default_price` so an invoice line can pick a procedure and get a price
without anyone re-typing it. It is NOT a rate card — no tiers, no codes, no
categories. Visits attach procedures to these items (4.3) and invoices price
their lines from them (5.2).

Two things this model establishes for the rest of the project:

- **Money is `Numeric`, NEVER float.** `default_price` is `Numeric(10, 2)`.
  Binary floating point cannot represent decimal currency exactly, and a rounding
  error in an invoice is a real-world bug. Python side: `Decimal`, never `float`.
- **Deactivate, never delete.** `active` hides an item from pickers while keeping
  the row readable, so historical visits/invoices that reference it still resolve.
  There is no DELETE route.

`name` is unique: duplicates ("Cleaning" three times) would make "revenue by
procedure" reporting meaningless, which is the whole reason this table exists.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class TreatmentItem(Base):
    __tablename__ = "treatment_item"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Unique so the catalogue can't accumulate duplicates of the same procedure.
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)

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
        return f"<TreatmentItem {self.name} {self.default_price}{'' if self.active else ' [inactive]'}>"
