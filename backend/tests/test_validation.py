"""Cross-cutting validation + data-routing tests (step 6.3).

The user asked to confirm that bad inputs are rejected and that data written via
the API comes back on the right screens. Most individual rules are covered in the
per-resource suites; this file adds a focused pass over the "reject bad data" and
"data lands on the right read" cases across resources, as a single guardrail.

Auth is faked (get_current_claims override) as elsewhere; skips fast without a DB.
Cleanup deletes everything this suite created, child-first.
"""

import io
import uuid
from datetime import datetime, timedelta, timezone

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
from app.models.patient_file import PatientFile
from app.models.payment import Payment
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit

client = TestClient(app)

BASE = datetime(2031, 6, 2, 10, 0, tzinfo=timezone.utc)


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
    def __init__(self, db, staff, patient, item):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.item = item
        self.client = client


@pytest.fixture
def ctx(db_available):
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(), name="Val Dentist", email=f"{uuid.uuid4()}@clinic.local",
        roles=["dentist", "admin"], active=True,
    )
    patient = Patient(name="Validation Patient")
    item = TreatmentItem(name=f"Val Item {uuid.uuid4().hex[:8]}", default_price="500.00")
    db.add_all([staff, patient, item])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    try:
        yield Ctx(db, staff, patient, item)
    finally:
        app.dependency_overrides.clear()
        _cleanup(db, staff, patient, item)
        db.close()


def _cleanup(db, staff, patient, item):
    db.rollback()
    pid = patient.id
    # child-first
    inv_ids = [i.id for i in db.scalars(select(Invoice).where(Invoice.patient_id == pid))]
    for iid in inv_ids:
        for p in db.scalars(select(Payment).where(Payment.invoice_id == iid)):
            db.delete(p)
        for ln in db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == iid)):
            db.delete(ln)
        db.commit()
        db.delete(db.get(Invoice, iid))
        db.commit()
    for f in db.scalars(select(PatientFile).where(PatientFile.patient_id == pid)):
        db.delete(f)
    for v in db.scalars(select(Visit).where(Visit.patient_id == pid)):
        for pr in db.scalars(select(ProcedurePerformed).where(ProcedurePerformed.visit_id == v.id)):
            db.delete(pr)
        db.commit()
        db.delete(v)
        db.commit()
    for a in db.scalars(select(Appointment).where(Appointment.patient_id == pid)):
        db.delete(a)
    for t in db.scalars(select(Treatment).where(Treatment.patient_id == pid)):
        db.delete(t)
    db.commit()
    for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == staff.id)):
        db.delete(row)
    db.commit()
    for obj in (db.get(Patient, pid), db.get(type(item), item.id), db.get(StaffUser, staff.id)):
        if obj is not None:
            db.delete(obj)
        db.commit()


# --- rejecting bad inputs ----------------------------------------------------

def test_patient_requires_name(ctx):
    assert ctx.client.post("/patients", json={"name": ""}).status_code == 422
    assert ctx.client.post("/patients", json={}).status_code == 422


def test_appointment_unknown_patient(ctx):
    resp = ctx.client.post(
        "/appointments",
        json={"patient_id": str(uuid.uuid4()), "start_time": BASE.isoformat()},
    )
    assert resp.status_code == 404


def test_appointment_bad_duration(ctx):
    resp = ctx.client.post(
        "/appointments",
        json={"patient_id": str(ctx.patient.id), "start_time": BASE.isoformat(), "duration_min": 0},
    )
    assert resp.status_code == 422


def test_appointment_overlap_conflict(ctx):
    dentist_id = str(ctx.staff.id)
    a = ctx.client.post(
        "/appointments",
        json={"patient_id": str(ctx.patient.id), "dentist_id": dentist_id,
              "start_time": BASE.isoformat(), "duration_min": 30},
    )
    assert a.status_code == 201
    # Same dentist, overlapping slot → 409.
    b = ctx.client.post(
        "/appointments",
        json={"patient_id": str(ctx.patient.id), "dentist_id": dentist_id,
              "start_time": (BASE + timedelta(minutes=15)).isoformat(), "duration_min": 30},
    )
    assert b.status_code == 409


def test_invoice_bad_payment_mode(ctx):
    """A payment mode outside the Literal is a 422."""
    # Build a visit + invoice quickly via the API.
    v = ctx.client.post(
        "/visits",
        json={"patient_id": str(ctx.patient.id), "treatment": {"title": "Val", "tooth_ref": None},
              "procedures": [{"treatment_item_id": str(ctx.item.id)}]},
    )
    assert v.status_code == 201, v.text
    inv = ctx.client.post(f"/visits/{v.json()['id']}/invoice", json={})
    assert inv.status_code == 201
    bad = ctx.client.post(
        f"/invoices/{inv.json()['id']}/payments", json={"amount": "100.00", "mode": "bitcoin"}
    )
    assert bad.status_code == 422


def test_file_bad_content_type(ctx):
    resp = ctx.client.post(
        f"/patients/{ctx.patient.id}/files",
        files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")},
        data={"kind": "document"},
    )
    assert resp.status_code == 415


# --- data routing: what's written comes back on the right read ---------------

def test_visit_shows_in_patient_history(ctx):
    v = ctx.client.post(
        "/visits",
        json={"patient_id": str(ctx.patient.id), "treatment": {"title": "History Check", "tooth_ref": "21"},
              "clinical_notes": "routed"},
    )
    assert v.status_code == 201
    hist = ctx.client.get(f"/visits?patient_id={ctx.patient.id}")
    assert hist.status_code == 200
    assert any(item["id"] == v.json()["id"] for item in hist.json()["items"])


def test_appointment_shows_in_day_list(ctx):
    a = ctx.client.post(
        "/appointments",
        json={"patient_id": str(ctx.patient.id), "start_time": BASE.isoformat(), "duration_min": 30},
    )
    assert a.status_code == 201
    day = BASE.date().isoformat()
    lst = ctx.client.get("/appointments", params={"date": day})
    assert lst.status_code == 200
    assert any(item["id"] == a.json()["id"] for item in lst.json()["items"])
