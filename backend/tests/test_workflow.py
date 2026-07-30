"""Workflow-correctness tests (step 6.8).

These pin the findings of the end-to-end walkthrough that prompted 6.8 — each
test here corresponds to a way the app previously let the clinic's data drift out
of step with reality:

- **Auto-close.** Recording a visit left its appointment at `arrived` forever, so
  the day view claimed patients were still in the chair.
- **The silently-ignored filter.** `GET /invoices?patient_id=` was not a declared
  param, so FastAPI dropped it and returned *every invoice in the clinic*. The
  tests here assert the filters **NARROW** the result — a weaker "returns 200"
  assertion is exactly what the broken version passed.
- **Invisible unbilled work.** Nothing listed visits with no invoice.
- **`done` with nothing recorded** — treated, or write-up forgotten?
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.services.billing import patient_balance

client = TestClient(app)


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
    def __init__(self, db, staff, patient, other_patient, item):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.other_patient = other_patient  # proves a filter really narrows
        self.item = item
        self.client = client


@pytest.fixture
def ctx(db_available):
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name="Workflow Dentist",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=["dentist", "admin"],
        active=True,
    )
    patient = Patient(name="Workflow Patient")
    other = Patient(name="Workflow Other Patient")
    item = TreatmentItem(
        name=f"Workflow Item {uuid.uuid4().hex[:8]}", default_price="800.00"
    )
    db.add_all([staff, patient, other, item])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}

    c = Ctx(db, staff, patient, other, item)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        db.rollback()
        pids = [patient.id, other.id]

        visit_ids = [v.id for v in db.scalars(select(Visit).where(Visit.patient_id.in_(pids)))]
        invoice_ids = [
            i.id for i in db.scalars(select(Invoice).where(Invoice.patient_id.in_(pids)))
        ]
        for iid in invoice_ids:
            for pay in db.scalars(select(Payment).where(Payment.invoice_id == iid)):
                db.delete(pay)
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
        for appt in db.scalars(select(Appointment).where(Appointment.patient_id.in_(pids))):
            db.delete(appt)
            db.commit()
        for t in db.scalars(select(Treatment).where(Treatment.patient_id.in_(pids))):
            db.delete(t)
            db.commit()
        for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == staff.id)):
            db.delete(row)
        db.commit()
        for model, oid in [
            (TreatmentItem, item.id),
            (Patient, patient.id),
            (Patient, other.id),
            (StaffUser, staff.id),
        ]:
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _book(ctx: Ctx, *, patient=None, hours=2, status="booked") -> str:
    """Book an appointment and return its id, optionally advancing its status."""
    when = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0)
    resp = ctx.client.post(
        "/appointments",
        json={
            "patient_id": str((patient or ctx.patient).id),
            "dentist_id": str(ctx.staff.id),
            "start_time": when.isoformat(),
            "duration_min": 30,
            "reason": "Workflow test",
        },
    )
    assert resp.status_code == 201, resp.text
    appt_id = resp.json()["id"]
    if status != "booked":
        r = ctx.client.post(f"/appointments/{appt_id}/status", json={"status": status})
        assert r.status_code == 200, r.text
    return appt_id


def _record_visit(ctx: Ctx, *, appointment_id=None, patient=None, completed=True) -> dict:
    body = {
        "patient_id": str((patient or ctx.patient).id),
        "treatment": {"title": "Workflow treatment", "tooth_ref": None},
        "procedures": [{"treatment_item_id": str(ctx.item.id), "tooth_ref": None}],
        "treatment_status": "completed" if completed else "in_progress",
    }
    if appointment_id:
        body["appointment_id"] = appointment_id
    resp = ctx.client.post("/visits", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- auto-close: recording a visit finishes the appointment ------------------

def test_recording_a_visit_closes_its_appointment(ctx):
    """The headline 6.8 fix: no separate 'mark done' step to forget."""
    appt_id = _book(ctx, status="arrived")
    _record_visit(ctx, appointment_id=appt_id)

    after = ctx.client.get(f"/appointments/{appt_id}").json()
    assert after["status"] == "done"


def test_auto_close_works_straight_from_booked(ctx):
    """A busy clinic treats the patient whether or not anyone clicked 'arrived'.
    The visit is proof both happened, so the auto-close walks booked -> done."""
    appt_id = _book(ctx, status="booked")
    _record_visit(ctx, appointment_id=appt_id)
    assert ctx.client.get(f"/appointments/{appt_id}").json()["status"] == "done"


def test_manual_status_endpoint_stays_strict(ctx):
    """The auto-close relaxation must NOT leak into the manual endpoint —
    check-in is still a real step, so booked -> done by hand is still a 409."""
    appt_id = _book(ctx, status="booked")
    resp = ctx.client.post(f"/appointments/{appt_id}/status", json={"status": "done"})
    assert resp.status_code == 409


def test_auto_close_is_audited(ctx):
    appt_id = _book(ctx, status="arrived")
    _record_visit(ctx, appointment_id=appt_id)

    rows = list(
        ctx.db.scalars(
            select(AuditLog).where(
                AuditLog.entity == "appointment",
                AuditLog.entity_id == uuid.UUID(appt_id),
                AuditLog.action == "status",
            )
        )
    )
    assert rows, "the auto-close should leave an audit trail"
    assert any((r.details or {}).get("auto_closed_by_visit") for r in rows)


def test_cancelled_appointment_is_not_resurrected(ctx):
    """`cancelled` is terminal by design (3.5). A visit against one is a
    data-entry problem for a human — never silently un-cancel it."""
    appt_id = _book(ctx, status="cancelled")
    _record_visit(ctx, appointment_id=appt_id)

    assert ctx.client.get(f"/appointments/{appt_id}").json()["status"] == "cancelled"


def test_no_show_appointment_is_not_resurrected(ctx):
    appt_id = _book(ctx, status="no_show")
    _record_visit(ctx, appointment_id=appt_id)
    assert ctx.client.get(f"/appointments/{appt_id}").json()["status"] == "no_show"


def test_walk_in_visit_touches_no_appointment(ctx):
    """A walk-in has no appointment; recording one must not fail or invent one."""
    visit = _record_visit(ctx, appointment_id=None)
    assert visit["appointment_id"] is None


# --- the silently-ignored filter (the data-ambiguity bug) --------------------

def test_invoices_patient_filter_actually_narrows(ctx):
    """THE regression. Before 6.8 this param was undeclared, so FastAPI dropped
    it and the endpoint returned every invoice in the clinic. Asserting only
    "200 OK" would have passed against the bug — so assert the OTHER patient's
    invoice is absent."""
    mine = _record_visit(ctx)
    theirs = _record_visit(ctx, patient=ctx.other_patient)
    inv_mine = ctx.client.post(f"/visits/{mine['id']}/invoice", json={}).json()
    inv_theirs = ctx.client.post(f"/visits/{theirs['id']}/invoice", json={}).json()

    resp = ctx.client.get(f"/invoices?patient_id={ctx.patient.id}")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["items"]}

    assert inv_mine["id"] in ids
    assert inv_theirs["id"] not in ids, "the filter leaked another patient's invoice"
    assert all(r["patient_id"] == str(ctx.patient.id) for r in resp.json()["items"])


def test_appointments_patient_filter_actually_narrows(ctx):
    mine = _book(ctx)
    theirs = _book(ctx, patient=ctx.other_patient, hours=5)

    resp = ctx.client.get(f"/appointments?patient_id={ctx.patient.id}")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["items"]}
    assert mine in ids
    assert theirs not in ids


def test_appointments_patient_filter_needs_no_date(ctx):
    """The profile asks "when are they next in?" without knowing a date."""
    _book(ctx, hours=24 * 30)  # a month out — outside any day/week view
    resp = ctx.client.get(f"/appointments?patient_id={ctx.patient.id}")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


def test_appointments_rejects_patient_id_with_a_date(ctx):
    """Mixing the two forms is a caller bug — fail loudly, don't guess."""
    resp = ctx.client.get(
        f"/appointments?patient_id={ctx.patient.id}&date=2026-07-30"
    )
    assert resp.status_code == 422


def test_appointments_still_requires_one_form(ctx):
    assert ctx.client.get("/appointments").status_code == 422


# --- unbilled worklist -------------------------------------------------------

def test_unbilled_lists_a_visit_with_no_invoice(ctx):
    visit = _record_visit(ctx)
    resp = ctx.client.get("/visits/unbilled")
    assert resp.status_code == 200

    row = next((r for r in resp.json()["items"] if r["id"] == visit["id"]), None)
    assert row is not None
    assert row["patient_name"] == "Workflow Patient"
    assert row["treatment_title"] == "Workflow treatment"
    assert row["procedure_count"] == 1


def test_billing_a_visit_removes_it_from_unbilled(ctx):
    """The worklist must empty as work gets done, or it becomes noise."""
    visit = _record_visit(ctx)
    assert visit["id"] in {r["id"] for r in ctx.client.get("/visits/unbilled").json()["items"]}

    ctx.client.post(f"/visits/{visit['id']}/invoice", json={})

    assert visit["id"] not in {
        r["id"] for r in ctx.client.get("/visits/unbilled").json()["items"]
    }


def test_unbilled_not_shadowed_by_id_route(ctx):
    """`/visits/unbilled` must be declared before `/visits/{visit_id}` or the
    literal parses as a UUID and 422s (the 4.8 / 5.5 / 6.6 trap)."""
    assert ctx.client.get("/visits/unbilled").status_code == 200


# --- 'done' with nothing recorded --------------------------------------------

def test_missing_visit_flags_done_appointments_with_no_visit(ctx):
    """Genuinely ambiguous: treated, or the write-up forgotten? Surface it."""
    bare = _book(ctx, status="arrived")
    ctx.client.post(f"/appointments/{bare}/status", json={"status": "done"})

    treated = _book(ctx, hours=4, status="arrived")
    _record_visit(ctx, appointment_id=treated)  # auto-closes to done

    today = datetime.now(timezone.utc).date().isoformat()
    resp = ctx.client.get(f"/appointments?date={today}&missing_visit=true")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["items"]}

    assert bare in ids, "a done appointment with no visit should be flagged"
    assert treated not in ids, "an appointment with a visit must NOT be flagged"


# --- patient balance ---------------------------------------------------------

def test_patient_balance_sums_across_invoices(ctx):
    v1 = _record_visit(ctx)
    v2 = _record_visit(ctx)
    i1 = ctx.client.post(f"/visits/{v1['id']}/invoice", json={}).json()
    i2 = ctx.client.post(f"/visits/{v2['id']}/invoice", json={}).json()

    # Pay one in full, the other partially.
    ctx.client.post(f"/invoices/{i1['id']}/payments", json={"amount": i1["total"], "mode": "cash"})
    ctx.client.post(f"/invoices/{i2['id']}/payments", json={"amount": "300.00", "mode": "upi"})

    bal = patient_balance(ctx.db, ctx.patient.id)
    assert bal["invoice_count"] == 2
    assert bal["total_billed"] == Decimal("1600.00")  # 800 + 800
    assert bal["total_paid"] == Decimal("1100.00")  # 800 + 300
    assert bal["outstanding"] == Decimal("500.00")
    assert bal["unpaid_count"] == 1


def test_overpayment_does_not_mask_another_debt(ctx):
    """Summing per-invoice outstanding (each floored at 0), NOT billed-minus-paid:
    otherwise an overpayment on one bill cancels a real debt on another and the
    patient looks settled when they are not."""
    v1 = _record_visit(ctx)
    v2 = _record_visit(ctx)
    i1 = ctx.client.post(f"/visits/{v1['id']}/invoice", json={}).json()
    ctx.client.post(f"/visits/{v2['id']}/invoice", json={})

    # Massively overpay the first; leave the second untouched.
    ctx.client.post(f"/invoices/{i1['id']}/payments", json={"amount": "5000.00", "mode": "cash"})

    bal = patient_balance(ctx.db, ctx.patient.id)
    assert bal["outstanding"] == Decimal("800.00"), "the second invoice is still owed"
    assert bal["unpaid_count"] == 1


def test_balance_of_a_patient_with_no_invoices_is_zero(ctx):
    bal = patient_balance(ctx.db, ctx.other_patient.id)
    assert bal["total_billed"] == Decimal("0.00")
    assert bal["outstanding"] == Decimal("0.00")
    assert bal["invoice_count"] == 0
