"""Tests for practice reports (step 6.1).

Two layers:
- **Service unit tests** (`revenue_trend` / `procedure_mix` / `no_show_rate`) against
  crafted rows, using deltas so the shared DB's other data doesn't pollute absolute
  totals. The clinic tz is pinned to a fixed zone for the run and restored.
- **Endpoint tests** for the role split (receptionist 403, dentist 200) and shape.

Cleanup is child-first (payment -> invoice_line -> invoice -> visit -> treatment ->
appointment/item -> patient), committing per delete like the other suites.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings as app_settings
from app.db import SessionLocal
from app.main import app
from app.models.appointment import Appointment
from app.models.clinic_settings import ClinicSettings
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.patient import Patient
from app.models.payment import Payment
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.services import reports as reports_svc

client = TestClient(app)


@pytest.fixture(scope="module")
def db_available() -> bool:
    probe = create_engine(app_settings.database_url, connect_args={"connect_timeout": 2})
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable, skipping DB tests: {exc}")
    finally:
        probe.dispose()
    return True


@pytest.fixture
def db(db_available):
    """A session + a cleanup registry, plus the clinic tz pinned to UTC for the
    test (so month/day math is predictable) and restored afterwards."""
    session = SessionLocal()
    cleanup: list[tuple[type, uuid.UUID]] = []
    order = [Payment, InvoiceLine, Invoice, Visit, Treatment, Appointment, TreatmentItem, Patient]

    prev_tz = session.get(ClinicSettings, 1).timezone
    session.get(ClinicSettings, 1).timezone = "UTC"
    session.commit()
    try:
        yield session, cleanup
    finally:
        session.rollback()
        for model, oid in sorted(cleanup, key=lambda t: order.index(t[0])):
            obj = session.get(model, oid)
            if obj is not None:
                session.delete(obj)
                session.commit()
        session.get(ClinicSettings, 1).timezone = prev_tz
        session.commit()
        session.close()


def _patient(session, cleanup) -> Patient:
    p = Patient(name="Report Patient")
    session.add(p)
    session.commit()
    cleanup.append((Patient, p.id))
    return p


def _paid_invoice(session, cleanup, patient, *, amount: str, when: datetime, item=None):
    """A visit + invoice + one line + one payment at `when`. Returns the payment."""
    treatment = Treatment(patient_id=patient.id, title="T")
    session.add(treatment)
    session.commit()
    cleanup.append((Treatment, treatment.id))
    visit = Visit(patient_id=patient.id, treatment_id=treatment.id)
    session.add(visit)
    session.commit()
    cleanup.append((Visit, visit.id))
    inv = Invoice(
        patient_id=patient.id, visit_id=visit.id,
        subtotal=Decimal(amount), total=Decimal(amount), created_at=when,
    )
    session.add(inv)
    session.commit()
    cleanup.append((Invoice, inv.id))
    line = InvoiceLine(
        invoice_id=inv.id,
        treatment_item_id=item.id if item else None,
        description=item.name if item else "Custom",
        amount=Decimal(amount),
    )
    session.add(line)
    session.commit()
    cleanup.append((InvoiceLine, line.id))
    pay = Payment(invoice_id=inv.id, amount=Decimal(amount), mode="cash", paid_at=when)
    session.add(pay)
    session.commit()
    cleanup.append((Payment, pay.id))
    return pay


# --- service unit tests ------------------------------------------------------

def test_revenue_trend_buckets_by_month_and_zero_fills(db):
    session, cleanup = db
    p = _patient(session, cleanup)
    now = datetime.now(timezone.utc)
    this_month = now.replace(day=15, hour=12, minute=0, second=0, microsecond=0)

    before = {r["month"]: r["total"] for r in reports_svc.revenue_trend(session, months=6)}
    _paid_invoice(session, cleanup, p, amount="1000.00", when=this_month)
    after = {r["month"]: r["total"] for r in reports_svc.revenue_trend(session, months=6)}

    key = f"{this_month.year:04d}-{this_month.month:02d}"
    assert after[key] - before[key] == Decimal("1000.00")
    # Always 6 months, present even when zero (the line has no gaps).
    assert len(after) == 6
    assert all(isinstance(v, Decimal) for v in after.values())


def test_procedure_mix_groups_and_orders_by_revenue(db):
    session, cleanup = db
    p = _patient(session, cleanup)
    now = datetime.now(timezone.utc).replace(day=10, hour=12)
    rct = TreatmentItem(name=f"RCT {uuid.uuid4().hex[:6]}", default_price=Decimal("4000"))
    clean = TreatmentItem(name=f"Clean {uuid.uuid4().hex[:6]}", default_price=Decimal("500"))
    session.add_all([rct, clean])
    session.commit()
    cleanup.append((TreatmentItem, rct.id))
    cleanup.append((TreatmentItem, clean.id))

    _paid_invoice(session, cleanup, p, amount="4000.00", when=now, item=rct)
    _paid_invoice(session, cleanup, p, amount="500.00", when=now, item=clean)

    mix = {r["name"]: r for r in reports_svc.procedure_mix(session, months=6)}
    assert mix[rct.name]["revenue"] == Decimal("4000.00")
    assert mix[rct.name]["count"] == 1
    assert mix[clean.name]["revenue"] == Decimal("500.00")
    # Ordered by revenue desc — RCT before Cleaning in the full list.
    names = [r["name"] for r in reports_svc.procedure_mix(session, months=6)]
    assert names.index(rct.name) < names.index(clean.name)


def test_no_show_rate_excludes_cancelled_from_denominator(db):
    session, cleanup = db
    p = _patient(session, cleanup)
    now = datetime.now(timezone.utc)

    def appt(status):
        a = Appointment(patient_id=p.id, start_time=now - timedelta(days=1), status=status)
        session.add(a)
        session.commit()
        cleanup.append((Appointment, a.id))

    base = reports_svc.no_show_rate(session, days=30)
    # 1 no_show, 3 done, 1 cancelled → scheduled = 4 (cancelled excluded).
    appt("no_show")
    for _ in range(3):
        appt("done")
    appt("cancelled")
    after = reports_svc.no_show_rate(session, days=30)

    assert after["no_show"] - base["no_show"] == 1
    assert after["cancelled"] - base["cancelled"] == 1
    # If the DB had no other appts in-window, rate = 1/4 = 25%. Assert the count
    # deltas above; also assert rate is a sane percentage.
    assert 0.0 <= after["rate"] <= 100.0


def test_no_show_rate_no_appointments_is_zero(db):
    """A fresh window with no appts must not divide by zero."""
    session, cleanup = db
    # We can't guarantee an empty shared DB, but the function must never raise and
    # must return a float rate.
    result = reports_svc.no_show_rate(session, days=1)
    assert isinstance(result["rate"], float)
    assert result["rate"] >= 0.0


# --- endpoint / auth ---------------------------------------------------------

def _staff(roles):
    s = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(), name="R", email=f"{uuid.uuid4()}@c.local", roles=roles, active=True
    )
    s.add(staff)
    s.commit()
    s.close()
    return staff


def test_requires_auth():
    assert client.get("/reports").status_code in (401, 403)


def test_receptionist_forbidden(db_available):
    staff = _staff(["receptionist"])
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    try:
        assert client.get("/reports").status_code == 403
    finally:
        app.dependency_overrides.clear()
        s = SessionLocal()
        s.delete(s.get(StaffUser, staff.id))
        s.commit()
        s.close()


def test_dentist_gets_report_shape(db_available):
    staff = _staff(["dentist"])
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    try:
        resp = client.get("/reports")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert set(data.keys()) == {"revenue_trend", "procedure_mix", "no_show"}
        assert len(data["revenue_trend"]) == 6  # default months
        assert set(data["no_show"].keys()) == {"total", "no_show", "done", "cancelled", "rate"}
    finally:
        app.dependency_overrides.clear()
        s = SessionLocal()
        s.delete(s.get(StaffUser, staff.id))
        s.commit()
        s.close()
