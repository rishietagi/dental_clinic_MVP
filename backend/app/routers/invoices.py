"""Invoice endpoints — generation + read (step 5.2).

The first billing endpoints. An invoice is generated FROM a visit
(`POST /visits/{visit_id}/invoice`) — the visit's recorded procedures are the
source of truth — but the resource is the invoice, so it lives on its own router
that 5.3 (payments) and 5.4 (receipt) will extend.

**Auth: any active staff** (`get_current_staff`), unlike clinical writes. Billing is
the receptionist's job (BUILD_PLAN §2) — the front desk creates invoices and takes
payment; the dentist writes the clinical record. A test asserts a receptionist can
generate.

**One request = one transaction.** Generating writes the invoice, its lines, and an
audit row; they commit together. The generation rule (including the price snapshot
and the one-per-visit check) lives in `services/billing.py`, which raises domain
exceptions — this router owns the HTTP status codes, the 4.3 standing decision. The
UNIQUE on `invoice.visit_id` is the real one-per-visit guarantee; a race that slips
past the service's pre-check is caught here as an IntegrityError and mapped to the
same 409.

**Route note:** the POST path is `/visits/{visit_id}/invoice` while GET is
`/invoices/{invoice_id}`, so this router carries no prefix and each route spells its
full path. The POST does not collide with the visits router's `/visits/{id}` — the
trailing `/invoice` segment disambiguates.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_staff
from app.db import get_db
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.payment import Payment
from app.models.staff_user import StaffUser
from app.schemas.invoice import InvoiceGenerate, InvoiceRead, PaymentCreate
from app.services.audit import record_audit
from app.services.billing import (
    DiscountExceedsSubtotal,
    InvoiceAlreadyExists,
    InvoiceNotFound,
    NothingToInvoice,
    VisitNotFound,
    generate_invoice,
    invoice_balances,
    record_payment,
)

router = APIRouter(tags=["invoices"])


def _to_read(db: Session, invoice: Invoice) -> InvoiceRead:
    """Assemble the invoice response: the invoice, its lines, its payments, and the
    derived settlement figures (amount_paid / outstanding)."""
    lines = db.scalars(
        select(InvoiceLine)
        .where(InvoiceLine.invoice_id == invoice.id)
        .order_by(InvoiceLine.description)
    ).all()
    payments = db.scalars(
        select(Payment)
        .where(Payment.invoice_id == invoice.id)
        .order_by(Payment.paid_at)
    ).all()
    amount_paid, outstanding = invoice_balances(db, invoice)
    return InvoiceRead(
        id=invoice.id,
        patient_id=invoice.patient_id,
        visit_id=invoice.visit_id,
        subtotal=invoice.subtotal,
        discount=invoice.discount,
        total=invoice.total,
        status=invoice.status,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        amount_paid=amount_paid,
        outstanding=outstanding,
        lines=list(lines),
        payments=list(payments),
    )


@router.post(
    "/visits/{visit_id}/invoice",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invoice(
    visit_id: UUID,
    body: InvoiceGenerate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> InvoiceRead:
    """Generate the invoice for a visit from its procedures (+ any custom lines)."""
    try:
        invoice = generate_invoice(
            db,
            visit_id=visit_id,
            discount=body.discount,
            extra_lines=body.extra_lines,
        )
    except VisitNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found."
        ) from exc
    except InvoiceAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invoice already exists for this visit.",
        ) from exc
    except NothingToInvoice as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This visit has no procedures to invoice. Record procedures or add a line.",
        ) from exc
    except DiscountExceedsSubtotal as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The discount cannot be larger than the subtotal.",
        ) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="create",
        entity="invoice",
        entity_id=invoice.id,
        details=jsonable_encoder(
            {
                "visit_id": visit_id,
                "subtotal": invoice.subtotal,
                "discount": invoice.discount,
                "total": invoice.total,
            }
        ),
    )

    try:
        db.commit()
    except IntegrityError as exc:
        # Race backstop: a second request beat us past the pre-check. The UNIQUE on
        # visit_id is the real guarantee — same friendly 409.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invoice already exists for this visit.",
        ) from exc

    db.refresh(invoice)
    return _to_read(db, invoice)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    invoice_id: UUID,
    body: PaymentCreate,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> InvoiceRead:
    """Record a payment against an invoice and recompute its status.

    Taking payment is front-desk work (BUILD_PLAN §2), so this is any active staff,
    like invoice generation. Overpayment is allowed (status caps at `paid`); the new
    status is derived from the payment sum, never sent by the client.
    """
    try:
        invoice = record_payment(
            db, invoice_id=invoice_id, amount=body.amount, mode=body.mode
        )
    except InvoiceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found."
        ) from exc

    record_audit(
        db,
        actor_id=staff.id,
        action="payment",
        entity="payment",
        entity_id=invoice.id,  # the invoice settled — payments read via the invoice
        details=jsonable_encoder(
            {"amount": body.amount, "mode": body.mode, "status": invoice.status}
        ),
    )
    db.commit()
    db.refresh(invoice)
    return _to_read(db, invoice)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    staff: StaffUser = Depends(get_current_staff),
) -> InvoiceRead:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found."
        )
    return _to_read(db, invoice)
