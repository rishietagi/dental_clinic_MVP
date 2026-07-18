"""Endpoint tests for the appointment booking API (step 3.2).

DB-backed, on the test_patients.py template: fake auth by overriding
get_current_claims with `{"sub": <staff id>}`, skip fast if no database.

The interesting cases are the conflict rules — the whole point of this step is
that overlapping appointments for the same dentist cannot be booked, that the
guarantee lives in the DB (not just the app pre-check), and that the boundaries
(back-to-back slots, different/NULL dentist, cancelled slots) behave correctly.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.appointment import Appointment
from app.models.audit_log import AuditLog
from app.models.patient import Patient
from app.models.staff_user import StaffUser

client = TestClient(app)


# A fixed base time (UTC) so tests are deterministic regardless of when they run.
BASE = datetime(2030, 8, 2, 10, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_create_requires_auth():
    assert client.post("/appointments", json={}).status_code in (401, 403)


def test_list_requires_auth():
    assert client.get("/appointments", params={"date": "2030-08-02"}).status_code in (
        401,
        403,
    )


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


# Ids created during a test, cleaned up in FK-safe order (appointments first).
_appt_ids: list[uuid.UUID] = []
_patient_ids: list[uuid.UUID] = []
_dentist_ids: list[uuid.UUID] = []


@pytest.fixture
def as_staff(db_available):
    """A TestClient acting as a freshly-created active staff member.

    Yields (client, staff_id). Cleans up appointments, patients, extra dentist
    rows, this staff row, and any audit rows it produced.
    """
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name="Test Reception",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=["receptionist"],
        active=True,
    )
    db.add(staff)
    db.commit()

    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}

    try:
        yield client, staff.id
    finally:
        app.dependency_overrides.clear()
        for aid in _appt_ids:
            obj = db.get(Appointment, aid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        for pid in _patient_ids:
            obj = db.get(Patient, pid)
            if obj is not None:
                db.delete(obj)
        for did in _dentist_ids:
            obj = db.get(StaffUser, did)
            if obj is not None:
                db.delete(obj)
        for row in db.execute(
            select(AuditLog).where(AuditLog.actor_id == staff.id)
        ).scalars():
            db.delete(row)
        db.commit()
        _appt_ids.clear()
        _patient_ids.clear()
        _dentist_ids.clear()
        db.delete(db.get(StaffUser, staff.id))
        db.commit()
        db.close()


def _make_patient() -> uuid.UUID:
    db = SessionLocal()
    try:
        p = Patient(name="Appt Patient")
        db.add(p)
        db.commit()
        _patient_ids.append(p.id)
        return p.id
    finally:
        db.close()


def _make_dentist() -> uuid.UUID:
    db = SessionLocal()
    try:
        d = StaffUser(
            id=uuid.uuid4(),
            name="Dr Test",
            email=f"{uuid.uuid4()}@clinic.local",
            roles=["dentist"],
            active=True,
        )
        db.add(d)
        db.commit()
        _dentist_ids.append(d.id)
        return d.id
    finally:
        db.close()


def _book(client: TestClient, **body) -> "tuple[int, dict]":
    resp = client.post("/appointments", json=body)
    data = resp.json()
    if resp.status_code == 201:
        _appt_ids.append(uuid.UUID(data["id"]))
    return resp.status_code, data


def _audit_actions(actor_id: uuid.UUID, entity_id: uuid.UUID) -> set[str]:
    db = SessionLocal()
    try:
        return {
            a.action
            for a in db.execute(
                select(AuditLog).where(
                    AuditLog.actor_id == actor_id, AuditLog.entity_id == entity_id
                )
            ).scalars()
        }
    finally:
        db.close()


# --- create + read -----------------------------------------------------------

def test_create_and_audit(as_staff):
    client, staff_id = as_staff
    pid = _make_patient()
    did = _make_dentist()

    status_code, data = _book(
        client,
        patient_id=str(pid),
        dentist_id=str(did),
        start_time=_iso(BASE),
        duration_min=30,
        reason="Cleaning",
    )
    assert status_code == 201, data
    assert data["status"] == "booked"
    assert data["duration_min"] == 30
    assert data["reason"] == "Cleaning"

    assert "create" in _audit_actions(staff_id, uuid.UUID(data["id"]))


def test_create_defaults_duration(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    status_code, data = _book(client, patient_id=str(pid), start_time=_iso(BASE))
    assert status_code == 201, data
    assert data["duration_min"] == 30  # default
    assert data["dentist_id"] is None


def test_book_unknown_patient_404(as_staff):
    client, _ = as_staff
    status_code, _data = _book(
        client, patient_id=str(uuid.uuid4()), start_time=_iso(BASE)
    )
    assert status_code == 404


def test_get_and_404(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    _, data = _book(client, patient_id=str(pid), start_time=_iso(BASE))
    assert client.get(f"/appointments/{data['id']}").status_code == 200
    assert client.get(f"/appointments/{uuid.uuid4()}").status_code == 404


# --- conflict rules ----------------------------------------------------------

def test_overlap_same_dentist_conflicts(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    s1, _ = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s1 == 201
    # 10:15 overlaps 10:00–10:30 for the same dentist.
    s2, data2 = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE.replace(minute=15)), duration_min=30,
    )
    assert s2 == 409, data2


def test_back_to_back_ok(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    s1, _ = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s1 == 201
    # 10:30 starts exactly when the first ends — half-open [) means no overlap.
    s2, data2 = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE.replace(minute=30)), duration_min=30,
    )
    assert s2 == 201, data2


def test_different_dentist_no_conflict(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    d1 = _make_dentist()
    d2 = _make_dentist()

    s1, _ = _book(
        client, patient_id=str(pid), dentist_id=str(d1),
        start_time=_iso(BASE), duration_min=30,
    )
    s2, data2 = _book(
        client, patient_id=str(pid), dentist_id=str(d2),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s1 == 201
    assert s2 == 201, data2


def test_null_dentist_no_conflict(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    # Two overlapping unassigned appointments — allowed (no dentist to clash).
    s1, _ = _book(client, patient_id=str(pid), start_time=_iso(BASE), duration_min=30)
    s2, data2 = _book(
        client, patient_id=str(pid),
        start_time=_iso(BASE.replace(minute=15)), duration_min=30,
    )
    assert s1 == 201
    assert s2 == 201, data2


def test_cancelled_does_not_block(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    # Insert a CANCELLED appointment directly (no cancel endpoint until 3.5).
    db = SessionLocal()
    try:
        cancelled = Appointment(
            patient_id=pid, dentist_id=did, start_time=BASE,
            duration_min=30, status="cancelled",
        )
        db.add(cancelled)
        db.commit()
        _appt_ids.append(cancelled.id)
    finally:
        db.close()

    # The same slot is free again because the cancelled one is excluded.
    s, data = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s == 201, data


def test_db_constraint_is_the_backstop(as_staff):
    """Proof the guarantee is in the DB: bypass the router's pre-check and insert a
    conflicting row straight through the ORM — the constraint must reject it."""
    from sqlalchemy.exc import IntegrityError

    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    # First one via the API (so it's tracked/cleaned up).
    s1, _ = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s1 == 201

    db = SessionLocal()
    try:
        clash = Appointment(
            patient_id=pid, dentist_id=did,
            start_time=BASE.replace(minute=15), duration_min=30,
        )
        db.add(clash)
        with pytest.raises(IntegrityError):
            db.commit()  # the EXCLUDE constraint rejects it
        db.rollback()
    finally:
        db.close()


# --- list by day -------------------------------------------------------------

def test_list_by_day(as_staff):
    client, _ = as_staff
    pid = _make_patient()

    # Two on 2030-08-02, one on 2030-08-03 (all unassigned so none conflict).
    _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(hour=9)))
    _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(hour=11)))
    _book(
        client, patient_id=str(pid),
        start_time=_iso(BASE.replace(day=3, hour=9)),
    )

    body = client.get("/appointments", params={"date": "2030-08-02"}).json()
    assert body["total"] == 2
    times = [item["start_time"] for item in body["items"]]
    assert times == sorted(times)  # ordered by start_time


# --- reschedule --------------------------------------------------------------

def test_reschedule(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    _, a = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    # Move it later in the day — no conflict, 200.
    r = client.patch(
        f"/appointments/{a['id']}", json={"start_time": _iso(BASE.replace(hour=14))}
    )
    assert r.status_code == 200, r.text
    assert r.json()["start_time"].startswith("2030-08-02T14:00")


def test_reschedule_onto_another_conflicts(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    _, a1 = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    _, a2 = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE.replace(hour=14)), duration_min=30,
    )
    # Try to move a2 onto a1's slot — 409.
    r = client.patch(f"/appointments/{a2['id']}", json={"start_time": _iso(BASE)})
    assert r.status_code == 409, r.text


def test_reschedule_self_no_false_conflict(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    _, a = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    # PATCH the same start_time (no real move) — must NOT conflict with itself.
    r = client.patch(f"/appointments/{a['id']}", json={"start_time": _iso(BASE)})
    assert r.status_code == 200, r.text
