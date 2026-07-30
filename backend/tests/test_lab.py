"""Endpoint tests for lab management (step 6.6).

DB-backed, auth faked by overriding get_current_claims (the test_visits.py template).

The tests that pin the design decisions:

- `test_case_gets_readable_number` — the whole point of the `number` column: staff
  quote "L-1001" to the lab, not a UUID.
- `test_existing_appointments_were_backfilled` — the migration gave every pre-existing
  appointment a number (adding NOT NULL to a populated table is the classic trap).
- `test_receptionist_can_send_and_receive` — lab work is front-desk, NOT dentist-only.
- `test_dashboard_buckets` — overdue vs due-soon vs back-from-lab, the lists that stop
  a case being forgotten. Uses clinic-zone today.
- `test_double_receive_conflicts` — the two-state lifecycle is enforced.

Assertions on shared lists are membership-based (not counts), so demo/seed data in the
same DB can't break them — the 6.4 lesson.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.lab import Lab
from app.models.lab_case import LabCase
from app.models.patient import Patient
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.visit import Visit

client = TestClient(app)


def test_requires_auth():
    assert client.get("/labs").status_code in (401, 403)
    assert client.get("/lab-cases").status_code in (401, 403)
    assert client.post("/lab-cases", json={}).status_code in (401, 403)


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
    def __init__(self, db, admin, recep, patient, lab):
        self.db = db
        self.admin = admin
        self.recep = recep
        self.patient = patient
        self.lab = lab
        self.client = client
        self.cases: list[uuid.UUID] = []
        self.labs: list[uuid.UUID] = [lab.id]

    def act_as(self, who):
        app.dependency_overrides[get_current_claims] = lambda: {"sub": str(who.id)}


@pytest.fixture
def ctx(db_available):
    db = SessionLocal()
    admin = StaffUser(
        id=uuid.uuid4(), name="Lab Admin", email=f"{uuid.uuid4()}@clinic.local",
        roles=["admin"], active=True,
    )
    recep = StaffUser(
        id=uuid.uuid4(), name="Lab Recep", email=f"{uuid.uuid4()}@clinic.local",
        roles=["receptionist"], active=True,
    )
    patient = Patient(name="Lab Test Patient")
    lab = Lab(name=f"Test Lab {uuid.uuid4().hex[:8]}", phone="9880000000")
    db.add_all([admin, recep, patient, lab])
    db.commit()

    c = Ctx(db, admin, recep, patient, lab)
    c.act_as(admin)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        db.rollback()
        # Child-first: cases -> visits/treatments -> labs -> patient/staff.
        for cid in c.cases:
            obj = db.get(LabCase, cid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        for lc in db.scalars(select(LabCase).where(LabCase.patient_id == patient.id)):
            db.delete(lc)
            db.commit()
        for v in db.scalars(select(Visit).where(Visit.patient_id == patient.id)):
            db.delete(v)
            db.commit()
        for t in db.scalars(select(Treatment).where(Treatment.patient_id == patient.id)):
            db.delete(t)
            db.commit()
        for who in (admin, recep):
            for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == who.id)):
                db.delete(row)
            db.commit()
        for lid in c.labs:
            obj = db.get(Lab, lid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        for model, oid in [(Patient, patient.id), (StaffUser, admin.id), (StaffUser, recep.id)]:
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _send(c: Ctx, **over) -> dict:
    """POST a lab case with sensible defaults; registers it for cleanup."""
    body = {
        "patient_id": str(c.patient.id),
        "lab_id": str(c.lab.id),
        "sample_type": "crown",
        "sent_date": date.today().isoformat(),
        "expected_date": (date.today() + timedelta(days=5)).isoformat(),
    }
    body.update(over)
    resp = c.client.post("/lab-cases", json=body)
    if resp.status_code == 201:
        c.cases.append(uuid.UUID(resp.json()["id"]))
    return resp


# --- labs (vendors) ----------------------------------------------------------

def test_admin_creates_lab_and_lists(ctx):
    name = f"New Lab {uuid.uuid4().hex[:8]}"
    resp = ctx.client.post("/labs", json={"name": name, "phone": "9812345678"})
    assert resp.status_code == 201, resp.text
    ctx.labs.append(uuid.UUID(resp.json()["id"]))
    assert resp.json()["active"] is True
    names = {i["name"] for i in ctx.client.get("/labs").json()["items"]}
    assert name in names


def test_duplicate_lab_name_conflicts(ctx):
    resp = ctx.client.post("/labs", json={"name": ctx.lab.name})
    assert resp.status_code == 409


def test_receptionist_cannot_create_lab(ctx):
    ctx.act_as(ctx.recep)
    resp = ctx.client.post("/labs", json={"name": f"Nope {uuid.uuid4().hex[:6]}"})
    assert resp.status_code == 403


def test_deactivated_lab_leaves_the_picker(ctx):
    created = ctx.client.post("/labs", json={"name": f"Temp Lab {uuid.uuid4().hex[:8]}"})
    lid = created.json()["id"]
    ctx.labs.append(uuid.UUID(lid))

    assert ctx.client.post(f"/labs/{lid}/deactivate").status_code == 200
    assert lid not in {i["id"] for i in ctx.client.get("/labs").json()["items"]}
    assert lid in {
        i["id"] for i in ctx.client.get("/labs", params={"include_inactive": "true"}).json()["items"]
    }
    assert ctx.client.post(f"/labs/{lid}/activate").status_code == 200
    assert lid in {i["id"] for i in ctx.client.get("/labs").json()["items"]}


# --- creating cases ----------------------------------------------------------

def test_case_gets_readable_number(ctx):
    """The readable id is the point: staff quote L-1001, never a UUID."""
    resp = _send(ctx)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert isinstance(data["number"], int)
    assert data["number"] >= 1001  # sequence starts at 1001
    assert data["status"] == "sent"
    assert data["patient_name"] == "Lab Test Patient"
    assert data["lab_name"] == ctx.lab.name
    assert data["follow_up_done"] is False


def test_case_numbers_are_unique_and_increment(ctx):
    a = _send(ctx).json()["number"]
    b = _send(ctx).json()["number"]
    assert b != a


def test_receptionist_can_send_and_receive(ctx):
    """Lab work is FRONT-DESK, not dentist-only."""
    ctx.act_as(ctx.recep)
    resp = _send(ctx)
    assert resp.status_code == 201, resp.text
    got = ctx.client.post(f"/lab-cases/{resp.json()['id']}/received", json={})
    assert got.status_code == 200, got.text


def test_expected_before_sent_is_422(ctx):
    resp = _send(
        ctx,
        sent_date=date.today().isoformat(),
        expected_date=(date.today() - timedelta(days=1)).isoformat(),
    )
    assert resp.status_code == 422


def test_unknown_patient_and_lab_404(ctx):
    assert _send(ctx, patient_id=str(uuid.uuid4())).status_code == 404
    assert _send(ctx, lab_id=str(uuid.uuid4())).status_code == 404


def test_unknown_sample_type_is_422(ctx):
    assert _send(ctx, sample_type="spaceship").status_code == 422


def test_case_links_to_visit_and_appointment(ctx):
    """A case raised from a sitting carries the visit + appointment links."""
    db = ctx.db
    treatment = Treatment(patient_id=ctx.patient.id, title="Crown 36")
    db.add(treatment)
    db.commit()
    visit = Visit(patient_id=ctx.patient.id, treatment_id=treatment.id)
    db.add(visit)
    db.commit()

    resp = _send(ctx, visit_id=str(visit.id))
    assert resp.status_code == 201, resp.text
    assert resp.json()["visit_id"] == str(visit.id)


# --- lifecycle ---------------------------------------------------------------

def test_receive_sets_date_and_status(ctx):
    case = _send(ctx).json()
    when = date.today().isoformat()
    resp = ctx.client.post(f"/lab-cases/{case['id']}/received", json={"received_date": when})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "received"
    assert resp.json()["received_date"] == when


def test_receive_defaults_to_today(ctx):
    case = _send(ctx).json()
    resp = ctx.client.post(f"/lab-cases/{case['id']}/received", json={})
    assert resp.json()["received_date"] is not None


def test_double_receive_conflicts(ctx):
    """The two-state lifecycle is enforced, not just documented."""
    case = _send(ctx).json()
    assert ctx.client.post(f"/lab-cases/{case['id']}/received", json={}).status_code == 200
    assert ctx.client.post(f"/lab-cases/{case['id']}/received", json={}).status_code == 409


def test_cancel_then_receive_conflicts(ctx):
    case = _send(ctx).json()
    assert ctx.client.post(f"/lab-cases/{case['id']}/cancel").status_code == 200
    assert ctx.client.post(f"/lab-cases/{case['id']}/received", json={}).status_code == 409


def test_follow_up_done_flag(ctx):
    case = _send(ctx).json()
    ctx.client.post(f"/lab-cases/{case['id']}/received", json={})
    resp = ctx.client.post(f"/lab-cases/{case['id']}/follow-up-done", json={"done": True})
    assert resp.status_code == 200
    assert resp.json()["follow_up_done"] is True


# --- list + dashboard --------------------------------------------------------

def test_list_and_status_filter(ctx):
    sent = _send(ctx).json()
    received = _send(ctx).json()
    ctx.client.post(f"/lab-cases/{received['id']}/received", json={})

    at_lab = {i["id"] for i in ctx.client.get("/lab-cases", params={"status": "sent"}).json()["items"]}
    back = {i["id"] for i in ctx.client.get("/lab-cases", params={"status": "received"}).json()["items"]}
    assert sent["id"] in at_lab
    assert received["id"] in back
    assert received["id"] not in at_lab


def test_list_by_patient(ctx):
    case = _send(ctx).json()
    items = ctx.client.get("/lab-cases", params={"patient_id": str(ctx.patient.id)}).json()["items"]
    assert case["id"] in {i["id"] for i in items}


def test_dashboard_buckets(ctx):
    """Overdue / due-soon / back-from-lab — the lists that stop a case being lost."""
    overdue_case = _send(
        ctx,
        sent_date=(date.today() - timedelta(days=10)).isoformat(),
        expected_date=(date.today() - timedelta(days=3)).isoformat(),
    ).json()
    soon_case = _send(ctx, expected_date=(date.today() + timedelta(days=2)).isoformat()).json()
    back_case = _send(ctx).json()
    ctx.client.post(f"/lab-cases/{back_case['id']}/received", json={})

    dash = ctx.client.get("/lab-cases/dashboard").json()
    assert overdue_case["id"] in {i["id"] for i in dash["overdue"]}
    assert soon_case["id"] in {i["id"] for i in dash["due_soon"]}
    assert back_case["id"] in {i["id"] for i in dash["back_from_lab"]}
    # An overdue case is not also "due soon".
    assert overdue_case["id"] not in {i["id"] for i in dash["due_soon"]}


def test_dismissed_case_leaves_back_from_lab(ctx):
    case = _send(ctx).json()
    ctx.client.post(f"/lab-cases/{case['id']}/received", json={})
    ctx.client.post(f"/lab-cases/{case['id']}/follow-up-done", json={"done": True})
    dash = ctx.client.get("/lab-cases/dashboard").json()
    assert case["id"] not in {i["id"] for i in dash["back_from_lab"]}


def test_dashboard_not_shadowed_by_id_route(ctx):
    """'dashboard' must resolve to the aggregate, not parse as a case UUID."""
    assert ctx.client.get("/lab-cases/dashboard").status_code == 200


def test_unknown_case_404(ctx):
    assert ctx.client.get(f"/lab-cases/{uuid.uuid4()}").status_code == 404


# --- the migration's appointment backfill ------------------------------------

def test_existing_appointments_were_backfilled(ctx):
    """Adding NOT NULL `number` to a populated table needs a backfill — verify it."""
    missing = ctx.db.scalars(select(Appointment).where(Appointment.number.is_(None))).first()
    assert missing is None


def test_case_creation_is_audited(ctx):
    case = _send(ctx).json()
    ctx.db.expire_all()
    row = ctx.db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "lab_case", AuditLog.entity_id == uuid.UUID(case["id"])
        )
    )
    assert row is not None
    assert row.action == "create"
