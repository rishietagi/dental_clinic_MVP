"""Invoice request/response schemas (step 5.2).

Prices are `Decimal` throughout — never `float` (the 4.1 rule). Pydantic validates
the scale so an amount can't carry more precision than the `Numeric(10,2)` columns
hold.

The generation contract (5.2): an invoice is built from a visit's recorded
procedures, with the biller optionally adding **custom lines** (a typed description
+ amount, no catalogue item) and a whole-invoice discount. The lines the client
sends are *extra* — the procedures are auto-seeded server-side from the visit, so
the receptionist never re-types what the dentist already recorded.

`InvoiceLineRead.description` / `amount` are the **frozen** values snapshotted at
generation (the 5.1 decision), so re-reading an old invoice shows what was charged
then, not today's catalogue price.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineIn(BaseModel):
    """A custom line the biller adds by hand (e.g. an X-ray, a materials charge).

    Has no catalogue link — its description and amount are typed, and stored frozen
    on the invoice line exactly as given.
    """

    description: str = Field(min_length=1, description="What is being charged.")
    amount: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Line amount in rupees.",
    )


class InvoiceGenerate(BaseModel):
    """Body for POST /visits/{visit_id}/invoice.

    Both fields optional: the common case is an empty body, which bills exactly the
    visit's recorded procedures with no discount. `extra_lines` adds manual charges;
    `discount` applies to the whole invoice.
    """

    discount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Whole-invoice discount. Must not exceed the subtotal.",
    )
    extra_lines: list[InvoiceLineIn] = Field(
        default_factory=list,
        description="Custom lines to add on top of the visit's procedures.",
    )


class InvoiceLineRead(BaseModel):
    """One line as charged. description + amount are frozen snapshots."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Nullable: a custom (typed) line has no catalogue link; a procedure line does.
    treatment_item_id: UUID | None
    description: str
    amount: Decimal


class PaymentCreate(BaseModel):
    """Body for POST /invoices/{invoice_id}/payments — recording money in.

    `amount` is `ge=0` (matching the DB CHECK) rather than `gt=0`: a zero payment is
    permitted. `mode` is a Literal, so an unknown method is a 422 — the same
    app-level-enum pattern as appointment status (no DB enum to migrate later).
    """

    amount: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Amount paid, in rupees.",
    )
    mode: Literal["cash", "card", "upi"] = Field(description="How the patient paid.")


class PaymentRead(BaseModel):
    """One payment against an invoice."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    mode: str
    paid_at: datetime


class InvoiceRead(BaseModel):
    """Everything the API returns about one invoice: its lines, its payments, and
    the derived settlement figures.

    `status` is always derived from the payment sum (unpaid / partially_paid /
    paid), never set by hand. `amount_paid` is the true sum (may exceed `total` when
    overpaid); `outstanding` floors at 0 so it's never negative.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    visit_id: UUID
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    amount_paid: Decimal
    outstanding: Decimal

    lines: list[InvoiceLineRead]
    payments: list[PaymentRead]


class InvoiceListItem(BaseModel):
    """A row in the Invoices list — the invoice plus the patient's name and the
    derived balance figures, so the list shows who owes what at a glance."""

    id: UUID
    patient_id: UUID
    patient_name: str
    total: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    status: str
    created_at: datetime


class InvoiceListResponse(BaseModel):
    items: list[InvoiceListItem]
    total: int


class CollectionsRead(BaseModel):
    """Today's collections for the dashboard (5.5).

    `date` is the clinic-local calendar day the figures cover. `total` and each
    `by_mode` value are Decimal (serialized as strings). `by_mode` always carries
    every payment mode (0.00 if none taken), so the card's layout is stable.
    """

    date: date
    total: Decimal
    count: int
    by_mode: dict[str, Decimal]
