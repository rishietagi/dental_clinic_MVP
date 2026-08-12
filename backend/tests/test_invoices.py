"""Endpoint tests for invoice generation + read (step 5.2).

DB-backed, on the test_visits.py template (auth faked by overriding
get_current_claims; skips fast without a database).

The headline tests pin the 5.1/5.2 decisions into behaviour:

- `test_generate_from_procedures` — the main path: a visit's procedures become
  priced lines, subtotal/total computed.
- `test_line_price_is_frozen` — the snapshot rule. Rename + reprice the catalogue
  item AFTER generating; the invoice still reads the price charged then.
- `test_custom_line_only` — a walk-in with no recorded procedures can still be
  billed by typing a line (the "custom invoice" case).
- `test_second_generate_conflicts` — one invoice per visit (the UNIQUE).
- `test_receptionist_can_generate` — billing is front-desk, not role-split like
  clinical writes.

Cleanup runs child-first (payments/lines -> invoices -> procedures -> visits ->
treatments -> patients) and commits per delete, because SQLAlchemy reorders a
batched flush and trips the FKs.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.clinic_settings import ClinicSettings
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit

client = TestClient(app)


def test_requires_auth():
    assert client.post(f"/visits/{uuid.uuid4()}/invoice", json={}).status_code in (401, 403)
    assert client.get(f"/invoices/{uuid.uuid4()}").status_code in (401, 403)


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


class Ctx:
    """The client, the acting staff, a patient, and three catalogue items.

    `item_med` is a **medicine** (6.7): it must bill through exactly the same
    procedure -> invoice-line pipeline as a treatment.
    """

    def __init__(self, db, staff, patient, item_a, item_b, item_med):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.item_a = item_a
        self.item_b = item_b
        self.item_med = item_med
        self.client = client


def _make_ctx(roles: list[str]) -> Ctx:
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name=f"Test {'/'.join(roles)}",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=roles,
        active=True,
    )
    patient = Patient(name="Invoice Test Patient")
    item_a = TreatmentItem(name=f"RCT {uuid.uuid4().hex[:8]}", default_price="4000.00")
    item_b = TreatmentItem(name=f"Scaling {uuid.uuid4().hex[:8]}", default_price="1500.00")
    item_med = TreatmentItem(
        name=f"Amoxicillin {uuid.uuid4().hex[:8]}",
        default_price="45.00",
        kind="medicine",
    )
    db.add_all([staff, patient, item_a, item_b, item_med])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    return Ctx(db, staff, patient, item_a, item_b, item_med)


def _cleanup(ctx: Ctx) -> None:
    app.dependency_overrides.clear()
    db = ctx.db
    db.rollback()

    patient_ids = [ctx.patient.id]
    visit_ids = [
        v.id for v in db.scalars(select(Visit).where(Visit.patient_id.in_(patient_ids)))
    ]

    # Invoices (+ their lines + payments) first — they reference visits.
    invoice_ids = [
        i.id for i in db.scalars(select(Invoice).where(Invoice.visit_id.in_(visit_ids)))
    ] if visit_ids else []
    for iid in invoice_ids:
        for pay in db.scalars(select(Payment).where(Payment.invoice_id == iid)):
            db.delete(pay)
            db.commit()
        for line in db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == iid)):
            db.delete(line)
            db.commit()
        db.delete(db.get(Invoice, iid))
        db.commit()

    for vid in visit_ids:
        for proc in db.scalars(
            select(ProcedurePerformed).where(ProcedurePerformed.visit_id == vid)
        ):
            db.delete(proc)
            db.commit()
        db.delete(db.get(Visit, vid))
        db.commit()
    for t in db.scalars(select(Treatment).where(Treatment.patient_id.in_(patient_ids))):
        db.delete(t)
        db.commit()
    for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == ctx.staff.id)):
        db.delete(row)
        db.commit()
    for model, oid in [
        (TreatmentItem, ctx.item_a.id),
        (TreatmentItem, ctx.item_b.id),
        (TreatmentItem, ctx.item_med.id),
        (Patient, ctx.patient.id),
        (StaffUser, ctx.staff.id),
    ]:
        obj = db.get(model, oid)
        if obj is not None:
            db.delete(obj)
            db.commit()
    db.close()


@pytest.fixture
def as_receptionist(db_available):
    ctx = _make_ctx(["receptionist"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


@pytest.fixture
def as_admin(db_available):
    """An admin context — needed for `GET /invoices/collections` since 6.12.

    Everything else on this router stays any-active-staff; only the clinic-wide
    day total moved behind admin.
    """
    ctx = _make_ctx(["admin"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


@pytest.fixture
def as_dentist(db_available):
    ctx = _make_ctx(["dentist"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


def _record_visit(ctx: Ctx, *, procedures) -> str:
    """Create a visit + its procedures directly in the DB, return the visit id.

    Recording a visit is dentist-write (4.3); this suite acts as a receptionist to
    prove billing is front-desk, so it builds the clinical rows directly rather than
    through the dentist-only /visits API. procedures = list of treatment_item ids.
    """
    db = ctx.db
    treatment = Treatment(patient_id=ctx.patient.id, title="RCT tooth 36", tooth_ref="36")
    db.add(treatment)
    db.commit()
    visit = Visit(patient_id=ctx.patient.id, treatment_id=treatment.id)
    db.add(visit)
    db.commit()
    for item_id in procedures:
        db.add(ProcedurePerformed(visit_id=visit.id, treatment_item_id=item_id))
    db.commit()
    return str(visit.id)


def _generate(ctx: Ctx, *, procedures, **body) -> dict:
    """Record a visit + generate its invoice; return the invoice JSON."""
    visit_id = _record_visit(ctx, procedures=procedures)
    resp = ctx.client.post(f"/visits/{visit_id}/invoice", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- generation --------------------------------------------------------------

def test_generate_from_procedures(as_receptionist):
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id, ctx.item_b.id])

    resp = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["visit_id"] == visit_id
    assert data["patient_id"] == str(ctx.patient.id)
    assert data["status"] == "unpaid"
    assert len(data["lines"]) == 2
    # Each line priced from the catalogue item's default_price.
    by_desc = {ln["description"]: ln for ln in data["lines"]}
    assert by_desc[ctx.item_a.name]["amount"] == "4000.00"
    assert by_desc[ctx.item_b.name]["amount"] == "1500.00"
    assert all(ln["treatment_item_id"] is not None for ln in data["lines"])
    assert data["subtotal"] == "5500.00"
    assert data["discount"] == "0.00"
    assert data["total"] == "5500.00"
    # A fresh invoice has no payments: nothing paid, the whole total outstanding.
    assert data["amount_paid"] == "0.00"
    assert data["outstanding"] == "5500.00"
    assert data["payments"] == []


def test_medicine_bills_like_a_treatment(as_receptionist):
    """A medicine (6.7) rides the same catalogue pipeline as a procedure.

    This is the regression that matters for the `kind` split: adding the column
    must not change how a line is priced, frozen, or linked. One bill carries a
    treatment and a medicine together — the clinic's actual case.
    """
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id, ctx.item_med.id])

    resp = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert resp.status_code == 201, resp.text
    data = resp.json()

    by_desc = {ln["description"]: ln for ln in data["lines"]}
    assert by_desc[ctx.item_a.name]["amount"] == "4000.00"
    assert by_desc[ctx.item_med.name]["amount"] == "45.00"
    # The medicine keeps its catalogue link, so it still lands in reports as a
    # named item rather than folding into "Other / custom".
    assert by_desc[ctx.item_med.name]["treatment_item_id"] == str(ctx.item_med.id)
    assert data["subtotal"] == "4045.00"
    assert data["total"] == "4045.00"


def test_consultation_fee_bills_as_a_custom_line(as_receptionist):
    """The per-dentist consultation fee has no catalogue row, so it reaches the
    invoice as an `extra_lines` entry (null treatment_item_id) — the mechanism
    5.2 already provided. No backend change was needed for it."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])

    resp = ctx.client.post(
        f"/visits/{visit_id}/invoice",
        json={
            "extra_lines": [
                {"description": "Consultation — Dr. Meera Prabhu", "amount": "300.00"}
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    consult = next(
        ln for ln in data["lines"] if ln["description"].startswith("Consultation")
    )
    assert consult["amount"] == "300.00"
    assert consult["treatment_item_id"] is None
    assert data["subtotal"] == "4300.00"


def test_line_price_is_frozen(as_receptionist):
    """After generating, renaming + repricing the item must NOT change the invoice."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])

    gen = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert gen.status_code == 201, gen.text
    invoice_id = gen.json()["id"]
    original_name = ctx.item_a.name

    # Reprice + rename the catalogue item after billing.
    item = ctx.db.get(TreatmentItem, ctx.item_a.id)
    item.name = f"Renamed {uuid.uuid4().hex[:8]}"
    item.default_price = "9999.99"
    ctx.db.commit()

    resp = ctx.client.get(f"/invoices/{invoice_id}")
    assert resp.status_code == 200
    line = resp.json()["lines"][0]
    assert line["description"] == original_name   # frozen label
    assert line["amount"] == "4000.00"            # frozen price
    assert resp.json()["total"] == "4000.00"


def test_custom_line_only(as_receptionist):
    """A visit with no procedures can still be billed with a typed line."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[])

    resp = ctx.client.post(
        f"/visits/{visit_id}/invoice",
        json={"extra_lines": [{"description": "X-ray", "amount": "300.00"}]},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["lines"]) == 1
    assert data["lines"][0]["description"] == "X-ray"
    assert data["lines"][0]["treatment_item_id"] is None  # custom line, no catalogue
    assert data["subtotal"] == "300.00"


def test_procedures_plus_custom_lines(as_receptionist):
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])

    resp = ctx.client.post(
        f"/visits/{visit_id}/invoice",
        json={"extra_lines": [{"description": "Materials", "amount": "250.00"}]},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["lines"]) == 2
    assert data["subtotal"] == "4250.00"  # 4000 + 250


def test_discount_applied(as_receptionist):
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])

    resp = ctx.client.post(
        f"/visits/{visit_id}/invoice", json={"discount": "500.00"}
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["subtotal"] == "4000.00"
    assert data["discount"] == "500.00"
    assert data["total"] == "3500.00"


def test_discount_exceeding_subtotal_rejected(as_receptionist):
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_b.id])  # subtotal 1500

    resp = ctx.client.post(
        f"/visits/{visit_id}/invoice", json={"discount": "2000.00"}
    )
    assert resp.status_code == 422, resp.text


def test_empty_invoice_rejected(as_receptionist):
    """0 procedures + 0 custom lines = nothing to charge."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[])

    resp = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert resp.status_code == 422, resp.text


def test_second_generate_conflicts(as_receptionist):
    """One invoice per visit — the UNIQUE surfaces as a 409."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])

    first = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert first.status_code == 201
    second = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert second.status_code == 409, second.text


def test_unknown_visit(as_receptionist):
    ctx = as_receptionist
    resp = ctx.client.post(f"/visits/{uuid.uuid4()}/invoice", json={})
    assert resp.status_code == 404, resp.text


def test_get_unknown_invoice(as_receptionist):
    ctx = as_receptionist
    resp = ctx.client.get(f"/invoices/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_receptionist_can_generate(as_receptionist):
    """Billing is the front desk's job — NOT role-split like clinical writes."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])
    resp = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert resp.status_code == 201, resp.text


def test_receptionist_can_still_bill_end_to_end_after_612(as_receptionist):
    """6.12 locked the money REPORTS to admin; it must not lock BILLING.

    This is the regression 6.12 could plausibly have caused, and it would break the
    front desk on day one: the receptionist must still generate an invoice, take a
    payment, read the invoice back, and browse the ledger. Only the clinic-wide day
    total moved. If someone later "tidies up" by narrowing this router wholesale,
    this test is what should stop them.
    """
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])  # total 4000

    gen = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert gen.status_code == 201, gen.text
    invoice_id = gen.json()["id"]

    pay = ctx.client.post(
        f"/invoices/{invoice_id}/payments", json={"amount": "1000.00", "mode": "cash"}
    )
    assert pay.status_code == 201, pay.text

    read = ctx.client.get(f"/invoices/{invoice_id}")
    assert read.status_code == 200, read.text
    assert read.json()["outstanding"] == "3000.00"

    ledger = ctx.client.get("/invoices")
    assert ledger.status_code == 200, ledger.text
    assert any(i["id"] == invoice_id for i in ledger.json()["items"])


def test_generation_writes_audit_row(as_receptionist):
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])
    resp = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    invoice_id = uuid.UUID(resp.json()["id"])

    ctx.db.expire_all()
    row = ctx.db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "invoice", AuditLog.entity_id == invoice_id
        )
    )
    assert row is not None
    assert row.action == "create"


# --- payment capture (5.3) ---------------------------------------------------

def _pay(ctx: Ctx, invoice_id: str, amount: str, mode: str = "cash"):
    return ctx.client.post(
        f"/invoices/{invoice_id}/payments", json={"amount": amount, "mode": mode}
    )


def test_partial_payment(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])  # total 4000
    assert inv["status"] == "unpaid"

    resp = _pay(ctx, inv["id"], "1000.00")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "partially_paid"
    assert data["amount_paid"] == "1000.00"
    assert data["outstanding"] == "3000.00"
    assert len(data["payments"]) == 1
    assert data["payments"][0]["mode"] == "cash"


def test_full_payment_marks_paid(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])  # total 4000

    resp = _pay(ctx, inv["id"], "4000.00", mode="upi")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "paid"
    assert data["amount_paid"] == "4000.00"
    assert data["outstanding"] == "0.00"


def test_two_part_payments_sum_to_paid(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])  # total 4000

    assert _pay(ctx, inv["id"], "1500.00").json()["status"] == "partially_paid"
    final = _pay(ctx, inv["id"], "2500.00", mode="card").json()
    assert final["status"] == "paid"
    assert final["amount_paid"] == "4000.00"
    assert final["outstanding"] == "0.00"
    assert len(final["payments"]) == 2


def test_overpayment_allowed_outstanding_floors_at_zero(as_receptionist):
    """Overpayment is allowed: sum may exceed total, outstanding never goes negative."""
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_b.id])  # total 1500

    resp = _pay(ctx, inv["id"], "2000.00")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "paid"
    assert data["amount_paid"] == "2000.00"   # true sum, may exceed total
    assert data["outstanding"] == "0.00"      # floored, never negative


def test_zero_payment_allowed(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])

    resp = _pay(ctx, inv["id"], "0.00")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "unpaid"          # nothing actually paid
    assert data["amount_paid"] == "0.00"


def test_unknown_mode_rejected(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])
    resp = _pay(ctx, inv["id"], "100.00", mode="bitcoin")
    assert resp.status_code == 422, resp.text


def test_payment_on_unknown_invoice(as_receptionist):
    ctx = as_receptionist
    resp = _pay(ctx, str(uuid.uuid4()), "100.00")
    assert resp.status_code == 404, resp.text


def test_payment_requires_auth():
    resp = client.post(
        f"/invoices/{uuid.uuid4()}/payments", json={"amount": "100.00", "mode": "cash"}
    )
    assert resp.status_code in (401, 403)


def test_get_invoice_reflects_payments(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])  # total 4000
    _pay(ctx, inv["id"], "1000.00")

    resp = ctx.client.get(f"/invoices/{inv['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "partially_paid"
    assert data["amount_paid"] == "1000.00"
    assert data["outstanding"] == "3000.00"
    assert len(data["payments"]) == 1


def test_payment_writes_audit_row(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])
    _pay(ctx, inv["id"], "500.00")

    ctx.db.expire_all()
    row = ctx.db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "payment",
            AuditLog.entity_id == uuid.UUID(inv["id"]),
        )
    )
    assert row is not None
    assert row.action == "payment"


# --- invoice-by-visit read (5.4) ---------------------------------------------

def test_get_invoice_for_visit(as_receptionist):
    """A visit that has an invoice resolves to it (same body as GET by id)."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])
    gen = ctx.client.post(f"/visits/{visit_id}/invoice", json={})
    assert gen.status_code == 201
    invoice_id = gen.json()["id"]

    resp = ctx.client.get(f"/visits/{visit_id}/invoice")
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == invoice_id
    assert resp.json()["visit_id"] == visit_id


def test_get_invoice_for_visit_without_one(as_receptionist):
    """A visit with no invoice yet → 404 (the 'Generate invoice' state)."""
    ctx = as_receptionist
    visit_id = _record_visit(ctx, procedures=[ctx.item_a.id])
    resp = ctx.client.get(f"/visits/{visit_id}/invoice")
    assert resp.status_code == 404, resp.text


def test_get_invoice_for_unknown_visit(as_receptionist):
    ctx = as_receptionist
    resp = ctx.client.get(f"/visits/{uuid.uuid4()}/invoice")
    assert resp.status_code == 404


# --- today's collections (5.5, admin-only since 6.12) ------------------------
#
# The test DB is shared, so other suites' payments may also fall on "today". These
# tests assert on the DELTA the payments they make cause, not absolute totals — the
# one exception is the route-shape/empty checks, which only look at structure.
#
# These all run `as_admin` now. The clinic-wide day total is an owner metric; the
# receptionist and dentist 403 cases are asserted separately below.

def _collections(ctx: Ctx) -> dict:
    resp = ctx.client.get("/invoices/collections")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_collections_shape(as_admin):
    ctx = as_admin
    data = _collections(ctx)
    assert set(data.keys()) == {"date", "total", "count", "by_mode"}
    # by_mode always carries all three modes for a stable card layout.
    assert set(data["by_mode"].keys()) == {"cash", "card", "upi"}


def test_collections_sums_todays_payments_by_mode(as_admin):
    ctx = as_admin
    inv = _generate(ctx, procedures=[ctx.item_a.id])  # total 4000

    before = _collections(ctx)
    _pay(ctx, inv["id"], "1000.00", mode="cash")
    _pay(ctx, inv["id"], "500.00", mode="card")
    _pay(ctx, inv["id"], "250.00", mode="upi")
    after = _collections(ctx)

    # Deltas isolate this test's payments from any other "today" data.
    assert _delta(after, before, "total") == Decimal("1750.00")
    assert after["count"] - before["count"] == 3
    assert _mode_delta(after, before, "cash") == Decimal("1000.00")
    assert _mode_delta(after, before, "card") == Decimal("500.00")
    assert _mode_delta(after, before, "upi") == Decimal("250.00")


def test_collections_counts_the_clinic_day_not_utc(as_admin):
    """A payment at an instant that is 'today' in the clinic zone but a different
    calendar day in UTC is counted for the clinic day — the 4.9 fix, for money."""
    ctx = as_admin
    db = ctx.db

    # Pin the clinic to IST and read what "today" is there.
    prev_tz = db.get(ClinicSettings, 1).timezone
    db.get(ClinicSettings, 1).timezone = "Asia/Kolkata"
    db.commit()
    try:
        ist = ZoneInfo("Asia/Kolkata")
        today_ist = datetime.now(ist).date()
        # 00:30 IST today = 19:00 UTC *yesterday* — a UTC-day query would miss it.
        instant = datetime(today_ist.year, today_ist.month, today_ist.day, 0, 30, tzinfo=ist)

        inv = _generate(ctx, procedures=[ctx.item_a.id])
        before = _collections(ctx)
        # Record via the API, then backdate paid_at to the crafted instant.
        resp = _pay(ctx, inv["id"], "700.00", mode="cash")
        assert resp.status_code == 201
        pay_id = uuid.UUID(resp.json()["payments"][-1]["id"])
        db.get(Payment, pay_id).paid_at = instant
        db.commit()

        after = _collections(ctx)
        assert after["date"] == today_ist.isoformat()
        assert _delta(after, before, "total") == Decimal("700.00")
    finally:
        db.get(ClinicSettings, 1).timezone = prev_tz
        db.commit()


def test_collections_requires_auth():
    assert client.get("/invoices/collections").status_code in (401, 403)


def test_collections_forbidden_for_receptionist(as_receptionist):
    """The front desk bills patients but must not see the clinic's day total (6.12)."""
    ctx = as_receptionist
    assert ctx.client.get("/invoices/collections").status_code == 403


def test_collections_forbidden_for_dentist(as_dentist):
    """A dentist login records clinical work; the takings are the owner's (6.12)."""
    ctx = as_dentist
    assert ctx.client.get("/invoices/collections").status_code == 403


def test_collections_not_shadowed_by_id_route(as_admin):
    """'collections' must resolve to the aggregate, not be parsed as an invoice id."""
    ctx = as_admin
    resp = ctx.client.get("/invoices/collections")
    assert resp.status_code == 200  # not 422 (uuid parse) or 404 (no such invoice)


def _delta(after: dict, before: dict, key: str) -> Decimal:
    return Decimal(after[key]) - Decimal(before[key])


def _mode_delta(after: dict, before: dict, mode: str) -> Decimal:
    return Decimal(after["by_mode"][mode]) - Decimal(before["by_mode"][mode])


# --- invoices list (6.4) -----------------------------------------------------

def test_list_invoices(as_receptionist):
    """A generated invoice shows up in GET /invoices with the patient name + balance."""
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])  # total 4000
    _pay(ctx, inv["id"], "1000.00", mode="cash")

    resp = ctx.client.get("/invoices")
    assert resp.status_code == 200, resp.text
    row = next((i for i in resp.json()["items"] if i["id"] == inv["id"]), None)
    assert row is not None
    assert row["patient_name"] == "Invoice Test Patient"
    assert row["total"] == "4000.00"
    assert row["amount_paid"] == "1000.00"
    assert row["outstanding"] == "3000.00"
    assert row["status"] == "partially_paid"
    assert "created_at" in row


def test_list_invoices_status_filter(as_receptionist):
    ctx = as_receptionist
    inv = _generate(ctx, procedures=[ctx.item_a.id])
    _pay(ctx, inv["id"], "4000.00", mode="upi")  # fully paid

    paid = ctx.client.get("/invoices", params={"status": "paid"}).json()["items"]
    assert any(i["id"] == inv["id"] for i in paid)
    unpaid = ctx.client.get("/invoices", params={"status": "unpaid"}).json()["items"]
    assert all(i["id"] != inv["id"] for i in unpaid)


def test_list_invoices_requires_auth():
    assert client.get("/invoices").status_code in (401, 403)


def test_list_not_shadowed_by_id_route(as_receptionist):
    """GET /invoices resolves to the list, not the {invoice_id} route."""
    ctx = as_receptionist
    assert ctx.client.get("/invoices").status_code == 200
