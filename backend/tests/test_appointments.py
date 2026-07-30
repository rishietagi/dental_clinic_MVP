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
from app.models.clinic_settings import ClinicSettings
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

    # Pin the clinic timezone to UTC for these tests: the day/range assertions
    # below use UTC-based times, so a "day" must mean a UTC day here. The IST
    # behaviour is tested separately (test_day_bounds_use_clinic_timezone). The
    # original zone is restored afterwards.
    _settings = db.get(ClinicSettings, 1)
    _saved_tz = _settings.timezone
    _settings.timezone = "UTC"
    db.commit()

    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}

    try:
        yield client, staff.id
    finally:
        app.dependency_overrides.clear()
        _settings = db.get(ClinicSettings, 1)
        _settings.timezone = _saved_tz
        db.commit()
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


def test_day_bounds_use_clinic_timezone(as_staff):
    """The 4.9 fix: 'a day' is a CLINIC day, not a UTC day.

    An appointment at 2026-08-01 19:30 UTC is 2026-08-02 01:00 in IST. With the
    clinic in Asia/Kolkata it must appear in the 2026-08-02 day query — even
    though its UTC date is the 1st. Under the old UTC-day bounds it would have
    been missed. Also confirm it does NOT show up on 2026-08-01 (its UTC date).
    """
    client, _ = as_staff
    pid = _make_patient()

    # Switch the clinic to IST for this test (the fixture pinned UTC).
    db = SessionLocal()
    try:
        s = db.get(ClinicSettings, 1)
        saved = s.timezone
        s.timezone = "Asia/Kolkata"
        db.commit()
    finally:
        db.close()

    try:
        # Measure as a DELTA rather than an absolute count: this suite shares the
        # dev database with the demo seed, which legitimately has appointments on
        # these dates. A test that only passes on an empty DB is fragile — real
        # data would break it too (the 6.4 lesson).
        before_2nd = client.get("/appointments", params={"date": "2026-08-02"}).json()["total"]
        before_1st = client.get("/appointments", params={"date": "2026-08-01"}).json()["total"]

        # 2026-08-01 19:30 UTC == 2026-08-02 01:00 IST (unassigned → no conflict).
        early_ist = datetime(2026, 8, 1, 19, 30, tzinfo=timezone.utc)
        _book(client, patient_id=str(pid), start_time=_iso(early_ist))

        on_2nd = client.get("/appointments", params={"date": "2026-08-02"}).json()
        assert on_2nd["total"] == before_2nd + 1, (
            "IST evening/early appt should fall on the clinic day"
        )
        assert str(pid) in {a["patient_id"] for a in on_2nd["items"]}

        on_1st = client.get("/appointments", params={"date": "2026-08-01"}).json()
        assert on_1st["total"] == before_1st, (
            "must not appear on its UTC date under IST bounds"
        )
        assert str(pid) not in {a["patient_id"] for a in on_1st["items"]}
    finally:
        db = SessionLocal()
        try:
            s = db.get(ClinicSettings, 1)
            s.timezone = saved
            db.commit()
        finally:
            db.close()


def test_list_items_carry_names(as_staff):
    """Day-list rows resolve patient_name (always) and dentist_name (or None)."""
    client, _ = as_staff
    did = _make_dentist()

    # One assigned appointment and one unassigned, same patient, same day.
    db = SessionLocal()
    try:
        dentist_name = db.get(StaffUser, did).name
    finally:
        db.close()

    # Distinct patients so we can match names unambiguously.
    db = SessionLocal()
    try:
        p_assigned = Patient(name="Assigned Patient")
        p_walkin = Patient(name="Walk-in Patient")
        db.add_all([p_assigned, p_walkin])
        db.commit()
        _patient_ids.extend([p_assigned.id, p_walkin.id])
        pid_assigned, pid_walkin = p_assigned.id, p_walkin.id
    finally:
        db.close()

    _book(
        client, patient_id=str(pid_assigned), dentist_id=str(did),
        start_time=_iso(BASE.replace(hour=9)), duration_min=30,
    )
    _book(client, patient_id=str(pid_walkin), start_time=_iso(BASE.replace(hour=11)))

    items = client.get("/appointments", params={"date": "2030-08-02"}).json()["items"]
    by_patient = {item["patient_name"]: item for item in items}

    assert by_patient["Assigned Patient"]["dentist_name"] == dentist_name
    assert by_patient["Walk-in Patient"]["dentist_name"] is None


def test_list_by_range(as_staff):
    """from/to returns appointments across the inclusive range, excluding outside."""
    client, _ = as_staff
    pid = _make_patient()

    # One on the 2nd, one on the 4th (inside), one on the 6th (outside the range).
    _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(day=2, hour=9)))
    _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(day=4, hour=9)))
    _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(day=6, hour=9)))

    body = client.get(
        "/appointments", params={"from": "2030-08-02", "to": "2030-08-04"}
    ).json()
    assert body["total"] == 2
    days = {item["start_time"][:10] for item in body["items"]}
    assert days == {"2030-08-02", "2030-08-04"}
    # Ordered by start_time.
    times = [item["start_time"] for item in body["items"]]
    assert times == sorted(times)


def test_list_range_boundaries_inclusive(as_staff):
    """Both endpoints of the range are inclusive (a single-day range = date=)."""
    client, _ = as_staff
    pid = _make_patient()
    _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(day=5, hour=23, minute=45)))

    body = client.get(
        "/appointments", params={"from": "2030-08-05", "to": "2030-08-05"}
    ).json()
    assert body["total"] == 1


def test_list_requires_exactly_one_form(as_staff):
    """Neither date nor from/to, or both, is a 422."""
    client, _ = as_staff
    # Neither.
    assert client.get("/appointments").status_code == 422
    # Both.
    assert client.get(
        "/appointments",
        params={"date": "2030-08-02", "from": "2030-08-02", "to": "2030-08-03"},
    ).status_code == 422
    # from without to (incomplete range) -> also 422.
    assert client.get("/appointments", params={"from": "2030-08-02"}).status_code == 422


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


# --- status workflow ---------------------------------------------------------

def _status(client, appt_id, status):
    return client.post(f"/appointments/{appt_id}/status", json={"status": status})


def test_status_requires_auth():
    assert client.post(
        f"/appointments/{uuid.uuid4()}/status", json={"status": "arrived"}
    ).status_code in (401, 403)


def test_status_happy_path(as_staff):
    """booked -> arrived -> done, each step 200, with audit rows."""
    client, staff_id = as_staff
    pid = _make_patient()
    _, a = _book(client, patient_id=str(pid), start_time=_iso(BASE))
    assert a["status"] == "booked"

    r1 = _status(client, a["id"], "arrived")
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "arrived"

    r2 = _status(client, a["id"], "done")
    assert r2.status_code == 200
    assert r2.json()["status"] == "done"

    # Both transitions audited (action="status").
    actions = _audit_actions(staff_id, uuid.UUID(a["id"]))
    assert "status" in actions


def test_status_offramps(as_staff):
    """booked -> cancelled, booked -> no_show, arrived -> no_show all legal."""
    client, _ = as_staff
    pid = _make_patient()

    _, a1 = _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(hour=9)))
    assert _status(client, a1["id"], "cancelled").status_code == 200

    _, a2 = _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(hour=10)))
    assert _status(client, a2["id"], "no_show").status_code == 200

    _, a3 = _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(hour=11)))
    assert _status(client, a3["id"], "arrived").status_code == 200
    assert _status(client, a3["id"], "no_show").status_code == 200


def test_illegal_transitions_conflict(as_staff):
    """Terminal states and same->same are 409."""
    client, _ = as_staff
    pid = _make_patient()

    _, a = _book(client, patient_id=str(pid), start_time=_iso(BASE))
    # booked -> booked (no real change) -> 409
    assert _status(client, a["id"], "booked").status_code == 409

    # Drive to done, then done -> arrived -> 409 (terminal).
    _status(client, a["id"], "arrived")
    _status(client, a["id"], "done")
    assert _status(client, a["id"], "arrived").status_code == 409

    # A cancelled appointment is terminal too.
    _, b = _book(client, patient_id=str(pid), start_time=_iso(BASE.replace(hour=13)))
    _status(client, b["id"], "cancelled")
    assert _status(client, b["id"], "booked").status_code == 409


def test_unknown_status_422(as_staff):
    client, _ = as_staff
    pid = _make_patient()
    _, a = _book(client, patient_id=str(pid), start_time=_iso(BASE))
    assert _status(client, a["id"], "banana").status_code == 422


def test_status_404_for_unknown_appointment(as_staff):
    client, _ = as_staff
    assert _status(client, str(uuid.uuid4()), "arrived").status_code == 404


def test_cancelling_frees_the_slot(as_staff):
    """Ties status to the booking rule: cancelling frees the slot for re-booking."""
    client, _ = as_staff
    pid = _make_patient()
    did = _make_dentist()

    _, a = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    # Same slot is taken while booked.
    s_conflict, _ = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s_conflict == 409

    # Cancel it → the slot frees.
    assert _status(client, a["id"], "cancelled").status_code == 200
    s_ok, _ = _book(
        client, patient_id=str(pid), dentist_id=str(did),
        start_time=_iso(BASE), duration_min=30,
    )
    assert s_ok == 201


# --- consulting dentist (6.3) ------------------------------------------------

def test_book_with_consulting_dentist(as_staff):
    """A second (consulting) dentist can be recorded on a booking, and comes back
    with its name resolved in the day list."""
    client, _staff_id = as_staff
    pid = _make_patient()
    primary = _make_dentist()
    consulting = _make_dentist()

    status_code, data = _book(
        client,
        patient_id=str(pid),
        dentist_id=str(primary),
        consulting_dentist_id=str(consulting),
        start_time=_iso(BASE),
        duration_min=30,
    )
    assert status_code == 201, data
    assert data["consulting_dentist_id"] == str(consulting)

    # The day list resolves both dentists' names.
    day = BASE.date().isoformat()
    items = client.get("/appointments", params={"date": day}).json()["items"]
    row = next(i for i in items if i["id"] == data["id"])
    assert row["dentist_name"] == "Dr Test"
    assert row["consulting_dentist_name"] == "Dr Test"
    assert row["consulting_dentist_id"] == str(consulting)


def test_consulting_dentist_optional(as_staff):
    """Omitting the consulting dentist is fine — most bookings have one dentist."""
    client, _staff_id = as_staff
    pid = _make_patient()
    primary = _make_dentist()
    status_code, data = _book(
        client, patient_id=str(pid), dentist_id=str(primary),
        start_time=_iso(BASE), duration_min=30,
    )
    assert status_code == 201
    assert data["consulting_dentist_id"] is None


def test_unknown_consulting_dentist_rejected(as_staff):
    """A consulting dentist id that isn't an active staff member is a 422."""
    client, _staff_id = as_staff
    pid = _make_patient()
    primary = _make_dentist()
    status_code, _ = _book(
        client,
        patient_id=str(pid),
        dentist_id=str(primary),
        consulting_dentist_id=str(uuid.uuid4()),
        start_time=_iso(BASE),
        duration_min=30,
    )
    assert status_code == 422
