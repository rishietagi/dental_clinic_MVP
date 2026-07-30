"""Invoice generation — building an invoice from a visit (step 5.2).

The **sixth `services/` module**. It holds the one rule Phase 5.2 cares about:
turn a recorded visit into a priced invoice, honouring the 5.1 decisions —

- **One invoice per visit** (ERD §9). The DB enforces it via a UNIQUE on
  `invoice.visit_id`; this pre-checks so the caller gets a friendly 409 instead of
  an IntegrityError, but the constraint is the real guarantee.
- **Lines snapshot their price.** Each of the visit's `procedure_performed` rows
  becomes an `invoice_line` carrying the catalogue item's **current** name and
  `default_price`, copied in — never read live later. A later rename/reprice of the
  item leaves this invoice untouched. This is the answer to the price-snapshot
  question deferred from 4.2.
- **Custom lines.** The biller may add typed lines (description + amount, no
  catalogue item) on top of the procedures — a walk-in with nothing recorded can
  still be billed by hand.

Like the other services (the 4.3 standing decision) this raises **domain
exceptions**, not `HTTPException`, so the rule is unit-testable without HTTP and the
router is the only place that maps to status codes. It `flush()`es but never
commits — the router owns the transaction, so the invoice, its lines and the audit
row land together or not at all.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinic_settings import ClinicSettings
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.payment import Payment
from app.models.procedure_performed import ProcedurePerformed
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.services.clinic import clinic_day_bounds


class VisitNotFound(Exception):
    """No visit with that id (router -> 404)."""


class InvoiceNotFound(Exception):
    """No invoice with that id (router -> 404)."""


class InvoiceAlreadyExists(Exception):
    """The visit already has an invoice (router -> 409).

    One invoice per visit (ERD §9). Editing or voiding an existing invoice is a
    later concern, not generation.
    """


class NothingToInvoice(Exception):
    """The visit has no procedures and no custom lines were given (router -> 422).

    A zero-line invoice has nothing to charge — almost always a sign the procedures
    weren't recorded yet.
    """


class DiscountExceedsSubtotal(Exception):
    """The requested discount is larger than the subtotal (router -> 422)."""


def _procedure_lines(db: Session, visit_id: UUID) -> list[InvoiceLine]:
    """Frozen lines from the visit's procedures, priced from the catalogue.

    Uses the same procedure->catalogue join as `routers/visits._load_procedures`.
    Name and price are copied onto the line here (the snapshot), so the line no
    longer depends on the item afterwards.
    """
    rows = db.execute(
        select(TreatmentItem.id, TreatmentItem.name, TreatmentItem.default_price)
        .join(ProcedurePerformed, ProcedurePerformed.treatment_item_id == TreatmentItem.id)
        .where(ProcedurePerformed.visit_id == visit_id)
        .order_by(TreatmentItem.name)
    ).all()
    return [
        InvoiceLine(
            treatment_item_id=item_id,
            description=name,
            amount=price,
        )
        for item_id, name, price in rows
    ]


def generate_invoice(
    db: Session,
    *,
    visit_id: UUID,
    discount: Decimal,
    extra_lines,  # list[schemas.invoice.InvoiceLineIn]
) -> Invoice:
    """Create the invoice for a visit. Returns it un-committed (router commits).

    Raises `VisitNotFound` / `InvoiceAlreadyExists` / `NothingToInvoice` /
    `DiscountExceedsSubtotal` — the router maps them to 404 / 409 / 422 / 422.
    """
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise VisitNotFound()

    # Friendly pre-check; the UNIQUE constraint is the real guarantee (a racing
    # second request is caught by the IntegrityError backstop in the router).
    existing = db.scalar(select(Invoice.id).where(Invoice.visit_id == visit_id))
    if existing is not None:
        raise InvoiceAlreadyExists()

    lines = _procedure_lines(db, visit_id)
    lines += [
        InvoiceLine(
            treatment_item_id=None,  # a typed line has no catalogue link
            description=extra.description,
            amount=extra.amount,
        )
        for extra in extra_lines
    ]

    if not lines:
        raise NothingToInvoice()

    subtotal = sum((line.amount for line in lines), Decimal("0"))
    if discount > subtotal:
        raise DiscountExceedsSubtotal()
    total = subtotal - discount

    invoice = Invoice(
        patient_id=visit.patient_id,
        visit_id=visit_id,
        subtotal=subtotal,
        discount=discount,
        total=total,
    )
    db.add(invoice)
    db.flush()  # assign invoice.id for the line FKs

    for line in lines:
        line.invoice_id = invoice.id
        db.add(line)
    db.flush()

    return invoice


# --- payment capture (5.3) ---------------------------------------------------

_CENTS = Decimal("0.01")


def _paid_sum(db: Session, invoice_id: UUID) -> Decimal:
    """Total paid against an invoice so far. Decimal, never float; 0 if none.

    Quantized to 2 places so the figure always carries cents ("0.00", not "0") —
    the money columns are Numeric(10,2), and the API formats every amount the same.
    """
    total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == invoice_id
        )
    )
    return Decimal(total).quantize(_CENTS)


def _recompute_status(db: Session, invoice: Invoice) -> None:
    """Set invoice.status from the payment sum. Derived state, never set by hand.

    unpaid (nothing paid) / partially_paid (some, below total) / paid (>= total).
    Overpayment is allowed, so the sum may exceed total — status just caps at paid.
    """
    paid = _paid_sum(db, invoice.id)
    if paid <= 0:
        invoice.status = "unpaid"
    elif paid < invoice.total:
        invoice.status = "partially_paid"
    else:
        invoice.status = "paid"


def invoice_balances(db: Session, invoice: Invoice) -> tuple[Decimal, Decimal]:
    """Return (amount_paid, outstanding) for an invoice.

    `amount_paid` is the true payment sum (may exceed total when overpaid).
    `outstanding` floors at 0 — a fully/over-paid invoice owes nothing, and a
    negative "outstanding" would be easy to misread.
    """
    paid = _paid_sum(db, invoice.id)
    outstanding = invoice.total - paid
    if outstanding < 0:
        outstanding = Decimal("0")
    return paid, outstanding.quantize(_CENTS)


def patient_balance(db: Session, patient_id: UUID) -> dict:
    """What this patient has been billed, has paid, and still owes (6.8).

    Powers the patient profile's Billing tab and its header figure. Aggregated
    from the existing invoices + payments — **no new column and no running
    total stored on the patient**, because a denormalised balance is exactly the
    kind of field that drifts out of step with the rows it summarises.

    `outstanding` sums the per-invoice outstanding (each already floored at 0 by
    `invoice_balances`) rather than `billed - paid`: otherwise an overpayment on
    one bill would silently cancel out a genuine debt on another and the patient
    would look settled when they are not.
    """
    invoices = list(db.scalars(select(Invoice).where(Invoice.patient_id == patient_id)))

    billed = sum((inv.total for inv in invoices), Decimal("0"))
    paid = Decimal("0")
    outstanding = Decimal("0")
    unpaid_count = 0
    for inv in invoices:
        inv_paid, inv_outstanding = invoice_balances(db, inv)
        paid += inv_paid
        outstanding += inv_outstanding
        if inv_outstanding > 0:
            unpaid_count += 1

    return {
        "total_billed": billed.quantize(_CENTS),
        "total_paid": paid.quantize(_CENTS),
        "outstanding": outstanding.quantize(_CENTS),
        "unpaid_count": unpaid_count,
        "invoice_count": len(invoices),
    }


def get_invoice_by_visit(db: Session, visit_id: UUID) -> Invoice | None:
    """The invoice for a visit, or None if it hasn't been generated yet.

    Lets a caller (the patient profile, 5.4) resolve a visit's billing state —
    "Generate invoice" vs "View invoice" — without a column on the visit. Cheap:
    `invoice.visit_id` is UNIQUE, so this is at most one row.
    """
    return db.scalar(select(Invoice).where(Invoice.visit_id == visit_id))


def record_payment(
    db: Session, *, invoice_id: UUID, amount: Decimal, mode: str
) -> Invoice:
    """Record a payment against an invoice and recompute its status.

    Returns the invoice un-committed (the router audits + commits — the house
    pattern). Raises `InvoiceNotFound` (router -> 404). Overpayment is allowed;
    a zero amount is allowed (the DB CHECK is amount >= 0).
    """
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceNotFound()

    db.add(Payment(invoice_id=invoice_id, amount=amount, mode=mode))
    db.flush()

    _recompute_status(db, invoice)
    db.flush()
    return invoice


# --- today's collections (5.5) -----------------------------------------------

# The payment modes we report a breakdown for. Kept in sync with the
# PaymentCreate Literal — a mode outside this set couldn't be recorded, but if the
# set ever grows, both places change together.
_COLLECTION_MODES = ("cash", "card", "upi")


def todays_collections(db: Session) -> dict:
    """Sum of payments taken on the clinic's TODAY, with a per-mode breakdown.

    "Today" is the clinic-local calendar day, not the server's or UTC's: a payment
    taken at 9pm IST must count for that clinic day, not slip into the next UTC day.
    We read the clinic timezone from `clinic_settings` (the same source
    `list_appointments` uses) and bound the day with `clinic_day_bounds` (4.9).

    Returns `{date, total, count, by_mode}` where `date` is the clinic-local date,
    `total`/`by_mode` values are `Decimal` quantized to cents (so they serialize as
    "0.00", not "0" — the 5.3 gotcha), and `by_mode` always carries all of
    cash/card/upi (0.00 if none), so the dashboard card's layout is stable.
    """
    tz_name = db.get(ClinicSettings, 1).timezone
    today = datetime.now(ZoneInfo(tz_name)).date()
    start, end = clinic_day_bounds(today, tz_name)

    in_today = (Payment.paid_at >= start) & (Payment.paid_at <= end)

    total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(in_today)
    )
    count = db.scalar(select(func.count()).select_from(Payment).where(in_today)) or 0

    grouped = db.execute(
        select(Payment.mode, func.coalesce(func.sum(Payment.amount), 0))
        .where(in_today)
        .group_by(Payment.mode)
    ).all()
    sums = {mode: amount for mode, amount in grouped}
    by_mode = {m: _cents(sums.get(m, 0)) for m in _COLLECTION_MODES}

    return {
        "date": today,
        "total": _cents(total),
        "count": count,
        "by_mode": by_mode,
    }


def _cents(value) -> Decimal:
    """Quantize a money value to 2 places so it serializes as '0.00', not '0'."""
    return Decimal(value).quantize(_CENTS)
