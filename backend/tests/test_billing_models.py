"""Tests for the billing models: invoice, invoice_line, payment (Phase 5.1).

DB-backed, so the suite skips fast if no Postgres is reachable — same pattern as
the other DB suites. These tables sit at the bottom of a chain
(patient -> visit, invoice -> invoice_line / payment), so cleanup runs
child-first.

Beyond the usual shape/defaults checks, the assertions worth having here pin the
domain rules of Phase 5 into the schema:

- **One invoice per visit** (ERD §9): the UNIQUE on `visit_id` makes a second
  invoice for the same visit impossible at the DB, not just in a service.
- **A line freezes its own description + amount** — the price-snapshot decision.
  Re-reading an invoice must show what was charged, independent of the catalogue.
- **`invoice_line.treatment_item_id` is nullable** — the reporting link is
  optional; the money lives on the line.
- **An invoice can have many payments** — part-payments are normal.
- **Money is Numeric/Decimal, never float**, and the hand-added CHECKs reject
  negative money and a discount larger than the subtotal.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal, engine
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit


@pytest.fixture(scope="module")
def db_available() -> bool:
    probe = create_engine(settings.database_url, connect_args={"connect_timeout": 2})
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable, skipping DB tests: {exc}")
    finally:
        probe.dispose()
    return True


# Delete order: children before the parents they point at.
_CLEANUP_ORDER = [
    Payment,
    InvoiceLine,
    Invoice,
    Visit,
    Treatment,
    TreatmentItem,
    Patient,
]


@pytest.fixture
def session(db_available):
    """Yields (db, cleanup) where cleanup is a list of (Model, id) to delete."""
    cleanup: list[tuple[type, uuid.UUID]] = []
    db = SessionLocal()
    try:
        yield db, cleanup
    finally:
        db.rollback()
        # Commit after each delete: a single commit at the end lets SQLAlchemy
        # choose its own flush order, which ignores _CLEANUP_ORDER and trips FKs.
        for model, oid in sorted(cleanup, key=lambda t: _CLEANUP_ORDER.index(t[0])):
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _make_visit(db, cleanup) -> Visit:
    """A patient + treatment + visit — the minimum an invoice hangs off."""
    patient = Patient(name="Billing Test Patient")
    db.add(patient)
    db.commit()
    cleanup.append((Patient, patient.id))

    treatment = Treatment(patient_id=patient.id, title="RCT tooth 36")
    db.add(treatment)
    db.commit()
    cleanup.append((Treatment, treatment.id))

    visit = Visit(patient_id=patient.id, treatment_id=treatment.id)
    db.add(visit)
    db.commit()
    cleanup.append((Visit, visit.id))
    return visit


def _make_item(db, cleanup, price="1200.50") -> TreatmentItem:
    item = TreatmentItem(
        name=f"Test Procedure {uuid.uuid4().hex[:8]}",  # name is unique
        default_price=Decimal(price),
    )
    db.add(item)
    db.commit()
    cleanup.append((TreatmentItem, item.id))
    return item


def _make_invoice(db, cleanup, visit, **kwargs) -> Invoice:
    inv = Invoice(patient_id=visit.patient_id, visit_id=visit.id, **kwargs)
    db.add(inv)
    db.commit()
    cleanup.append((Invoice, inv.id))
    return inv


# --- schema shape ------------------------------------------------------------

def test_migration_created_tables(db_available):
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    assert {"invoice", "invoice_line", "payment"} <= names

    invoice_cols = {c["name"] for c in inspector.get_columns("invoice")}
    assert {
        "id", "patient_id", "visit_id", "subtotal", "discount", "total",
        "status", "created_at", "updated_at",
    } <= invoice_cols

    line_cols = {c["name"] for c in inspector.get_columns("invoice_line")}
    assert {"id", "invoice_id", "treatment_item_id", "description", "amount"} <= line_cols

    payment_cols = {c["name"] for c in inspector.get_columns("payment")}
    assert {"id", "invoice_id", "amount", "mode", "paid_at"} <= payment_cols


def test_foreign_keys(db_available):
    inspector = inspect(engine)

    def referred(table: str) -> dict[tuple[str, ...], str]:
        return {
            tuple(fk["constrained_columns"]): fk["referred_table"]
            for fk in inspector.get_foreign_keys(table)
        }

    invoice_fks = referred("invoice")
    assert invoice_fks.get(("patient_id",)) == "patient"
    assert invoice_fks.get(("visit_id",)) == "visit"

    line_fks = referred("invoice_line")
    assert line_fks.get(("invoice_id",)) == "invoice"
    assert line_fks.get(("treatment_item_id",)) == "treatment_item"

    assert referred("payment").get(("invoice_id",)) == "invoice"


def test_invoice_nullability(db_available):
    """The line's catalogue link is optional; everything else on the money path isn't."""
    inspector = inspect(engine)

    invoice_nullable = {c["name"]: c["nullable"] for c in inspector.get_columns("invoice")}
    assert invoice_nullable["patient_id"] is False
    assert invoice_nullable["visit_id"] is False

    line_nullable = {c["name"]: c["nullable"] for c in inspector.get_columns("invoice_line")}
    assert line_nullable["invoice_id"] is False
    assert line_nullable["treatment_item_id"] is True   # reporting link only
    assert line_nullable["description"] is False
    assert line_nullable["amount"] is False


# --- persistence -------------------------------------------------------------

def test_invoice_defaults(session):
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(db, cleanup, visit)
    db.expire_all()

    fetched = db.get(Invoice, invoice.id)
    assert fetched is not None
    assert fetched.id is not None                 # server-generated
    assert fetched.status == "unpaid"             # server default
    assert fetched.subtotal == Decimal("0.00")    # server default
    assert fetched.discount == Decimal("0.00")
    assert fetched.total == Decimal("0.00")
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_invoice_is_one_per_visit(session):
    """The UNIQUE on visit_id: a second invoice for the same visit is rejected."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    _make_invoice(db, cleanup, visit)

    db.add(Invoice(patient_id=visit.patient_id, visit_id=visit.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invoice_visit_fk_is_enforced(session):
    """An invoice must reference a real visit."""
    db, cleanup = session
    patient = Patient(name="Billing FK Patient")
    db.add(patient)
    db.commit()
    cleanup.append((Patient, patient.id))

    db.add(Invoice(patient_id=patient.id, visit_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invoice_line_freezes_description_and_amount(session):
    """The price-snapshot rule: the line carries its own label + amount, and they
    do not change if the catalogue item is later renamed or repriced."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(db, cleanup, visit)
    item = _make_item(db, cleanup, price="1200.50")

    line = InvoiceLine(
        invoice_id=invoice.id,
        treatment_item_id=item.id,
        description="RCT (as charged 2 Aug)",
        amount=Decimal("1200.50"),
    )
    db.add(line)
    db.commit()
    cleanup.append((InvoiceLine, line.id))

    # Reprice + rename the catalogue item after the line was written.
    item.name = f"Renamed {uuid.uuid4().hex[:8]}"
    item.default_price = Decimal("9999.99")
    db.commit()
    db.expire_all()

    fetched = db.get(InvoiceLine, line.id)
    assert fetched is not None
    assert fetched.description == "RCT (as charged 2 Aug)"  # frozen label
    assert fetched.amount == Decimal("1200.50")            # frozen price
    assert fetched.treatment_item_id == item.id            # link intact


def test_invoice_line_treatment_item_nullable(session):
    """A line with no catalogue link persists — the money lives on the line."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(db, cleanup, visit)

    line = InvoiceLine(
        invoice_id=invoice.id,
        treatment_item_id=None,
        description="Ad-hoc charge",
        amount=Decimal("500.00"),
    )
    db.add(line)
    db.commit()  # would raise if treatment_item_id were required
    cleanup.append((InvoiceLine, line.id))
    db.expire_all()

    fetched = db.get(InvoiceLine, line.id)
    assert fetched is not None
    assert fetched.treatment_item_id is None
    assert fetched.amount == Decimal("500.00")


def test_invoice_line_fk_is_enforced(session):
    """A line must reference a real invoice."""
    db, cleanup = session
    db.add(
        InvoiceLine(
            invoice_id=uuid.uuid4(), description="orphan", amount=Decimal("1.00")
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_payment_fk_is_enforced(session):
    """A payment must reference a real invoice."""
    db, cleanup = session
    db.add(Payment(invoice_id=uuid.uuid4(), amount=Decimal("1.00"), mode="cash"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invoice_can_have_multiple_payments(session):
    """Part-payments: an invoice may be settled by several payments."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(db, cleanup, visit, total=Decimal("1000.00"))

    for amt, mode in ((Decimal("600.00"), "cash"), (Decimal("400.00"), "upi")):
        p = Payment(invoice_id=invoice.id, amount=amt, mode=mode)
        db.add(p)
        db.commit()
        cleanup.append((Payment, p.id))

    db.expire_all()
    payments = db.query(Payment).filter(Payment.invoice_id == invoice.id).all()
    assert len(payments) == 2
    assert sum(p.amount for p in payments) == Decimal("1000.00")
    assert {p.mode for p in payments} == {"cash", "upi"}


def test_money_round_trips_as_exact_decimal(session):
    """Money is Numeric/Decimal, never float — an exact decimal survives the DB."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(
        db, cleanup, visit,
        subtotal=Decimal("1200.50"),
        discount=Decimal("200.50"),
        total=Decimal("1000.00"),
    )
    db.expire_all()

    fetched = db.get(Invoice, invoice.id)
    assert fetched.subtotal == Decimal("1200.50")
    assert isinstance(fetched.subtotal, Decimal)
    assert fetched.discount == Decimal("200.50")
    assert fetched.total == Decimal("1000.00")


# --- the hand-added CHECK constraints ---------------------------------------

def test_negative_invoice_amount_rejected(session):
    """invoice_amounts_nonneg: negative money is refused by the DB."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    db.add(
        Invoice(
            patient_id=visit.patient_id,
            visit_id=visit.id,
            subtotal=Decimal("-1.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_discount_greater_than_subtotal_rejected(session):
    """invoice_discount_le_subtotal: a discount can't exceed the subtotal."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    db.add(
        Invoice(
            patient_id=visit.patient_id,
            visit_id=visit.id,
            subtotal=Decimal("100.00"),
            discount=Decimal("150.00"),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_negative_line_amount_rejected(session):
    """invoice_line_amount_nonneg: a negative line amount is refused."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(db, cleanup, visit)
    db.add(
        InvoiceLine(
            invoice_id=invoice.id, description="bad", amount=Decimal("-5.00")
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_negative_payment_amount_rejected(session):
    """payment_amount_nonneg: a negative payment is refused."""
    db, cleanup = session
    visit = _make_visit(db, cleanup)
    invoice = _make_invoice(db, cleanup, visit)
    db.add(Payment(invoice_id=invoice.id, amount=Decimal("-1.00"), mode="cash"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
