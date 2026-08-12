"""Endpoint tests for the patient CRUD API.

DB-backed. Auth is faked the same way as test_auth.py: override get_current_claims
to a `{"sub": <staff id>}` dict and create that staff row, so get_current_staff
resolves without a real ES256 token. Skips fast if no database is reachable.
"""

import uuid

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


def test_create_requires_auth():
    # No token / no override -> the auth dependency rejects it.
    assert client.post("/patients", json={"name": "X"}).status_code in (401, 403)


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


@pytest.fixture
def as_staff(db_available):
    """A TestClient acting as a freshly-created active staff member.

    Yields (client, staff_id). Cleans up the staff row, plus any patients and
    audit rows created during the test.
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
        # Clean up audit rows + patients this test created, then the staff row.
        for row in db.execute(select(AuditLog).where(AuditLog.actor_id == staff.id)).scalars():
            db.delete(row)
        # Appointments first — appointment.patient_id is a real FK, so deleting the
        # patient while one exists is a ForeignKeyViolation. Added in 6.13 when a
        # test here first needed to book.
        if _created_patient_ids:
            for appt in db.execute(
                select(Appointment).where(Appointment.patient_id.in_(_created_patient_ids))
            ).scalars():
                db.delete(appt)
            db.commit()
        for pid in _created_patient_ids:
            obj = db.get(Patient, pid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        _created_patient_ids.clear()
        db.delete(db.get(StaffUser, staff.id))
        db.commit()
        db.close()


_created_patient_ids: list[uuid.UUID] = []


def _create(client: TestClient, **body) -> dict:
    body.setdefault("name", "Asha Rao")
    resp = client.post("/patients", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    _created_patient_ids.append(uuid.UUID(data["id"]))
    return data


def _audit_rows(actor_id: uuid.UUID, entity_id: uuid.UUID) -> list[AuditLog]:
    db = SessionLocal()
    try:
        return list(
            db.execute(
                select(AuditLog).where(
                    AuditLog.actor_id == actor_id, AuditLog.entity_id == entity_id
                )
            ).scalars()
        )
    finally:
        db.close()


def test_create_patient_and_audit(as_staff):
    client, staff_id = as_staff
    data = _create(client, name="Asha Rao", phone="+919812345678", date_of_birth="1990-05-01")

    assert data["name"] == "Asha Rao"
    assert data["phone"] == "+919812345678"
    assert data["archived"] is False
    assert data["age"] is not None

    audits = _audit_rows(staff_id, uuid.UUID(data["id"]))
    assert any(a.action == "create" and a.entity == "patient" for a in audits)


def test_get_patient_and_404(as_staff):
    client, _ = as_staff
    data = _create(client)
    assert client.get(f"/patients/{data['id']}").status_code == 200
    assert client.get(f"/patients/{uuid.uuid4()}").status_code == 404


def test_patch_updates_only_given_fields(as_staff):
    client, staff_id = as_staff
    data = _create(client, name="Old Name", phone="111")

    resp = client.patch(f"/patients/{data['id']}", json={"phone": "222"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["phone"] == "222"
    assert updated["name"] == "Old Name"  # untouched

    audits = _audit_rows(staff_id, uuid.UUID(data["id"]))
    assert any(a.action == "update" and a.details == {"phone": "222"} for a in audits)


def test_archive_and_unarchive_are_soft(as_staff):
    client, staff_id = as_staff
    data = _create(client)
    pid = data["id"]

    assert client.post(f"/patients/{pid}/archive").json()["archived"] is True
    # Soft-delete: the row is still there and still fetchable.
    assert client.get(f"/patients/{pid}").status_code == 200
    assert client.get(f"/patients/{pid}").json()["archived"] is True

    assert client.post(f"/patients/{pid}/unarchive").json()["archived"] is False

    actions = {a.action for a in _audit_rows(staff_id, uuid.UUID(pid))}
    assert {"archive", "unarchive"} <= actions


# --- list + search -----------------------------------------------------------

def test_list_requires_auth():
    assert client.get("/patients").status_code in (401, 403)


def test_search_by_name_and_phone(as_staff):
    client, _ = as_staff
    # A unique token so the search only matches rows this test created, even if
    # the table holds patients from elsewhere.
    tag = uuid.uuid4().hex[:8]
    _create(client, name=f"Zerith {tag}", phone="+915550001111")
    _create(client, name=f"Other {tag}", phone="+915559998888")

    # name substring, case-insensitive
    r = client.get("/patients", params={"q": f"zerith {tag}"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == f"Zerith {tag}"
    # list items must NOT leak medical_notes
    assert "medical_notes" not in body["items"][0]

    # phone substring
    r = client.get("/patients", params={"q": "5559998888"})
    assert r.json()["total"] == 1

    # no match
    assert client.get("/patients", params={"q": f"nomatch{tag}"}).json()["total"] == 0


def test_search_treats_like_wildcards_literally(as_staff):
    """`%` and `_` are LIKE wildcards — the search must match them as characters.

    Found in the 6.13 check pass: unescaped, `q="%"` returned EVERY patient and
    `q="_"` matched any single character, so a phone search like `98_1` silently
    matched numbers the user never asked for. Not injection (the value is still
    parameterised) — just wrong results from a search box, which at a front desk
    is its own kind of bug.
    """
    client, _ = as_staff
    tag = uuid.uuid4().hex[:8]
    _create(client, name=f"Percent {tag} 100%", phone="+915551110000")
    _create(client, name=f"Plain {tag}", phone="+915552220000")

    everyone = client.get("/patients").json()["total"]

    # A bare wildcard must NOT return the whole table. It can legitimately match
    # other patients whose names contain a literal '%', so compare against the
    # unfiltered count rather than asserting zero — the shared test DB makes any
    # absolute number here a flake waiting to happen.
    wildcard = client.get("/patients", params={"q": "%"}).json()
    assert wildcard["total"] < everyone
    assert all("%" in p["name"] for p in wildcard["items"])

    underscore = client.get("/patients", params={"q": "_"}).json()
    assert underscore["total"] < everyone

    # A literal % in a name is findable, and only that patient comes back.
    hit = client.get("/patients", params={"q": f"{tag} 100%"}).json()
    assert hit["total"] == 1
    assert hit["items"][0]["name"] == f"Percent {tag} 100%"

    # `_` must not act as "any character": this would match "Plain <tag>" if it did.
    assert client.get("/patients", params={"q": f"Pla_n {tag}"}).json()["total"] == 0


def test_archived_hidden_by_default(as_staff):
    client, _ = as_staff
    tag = uuid.uuid4().hex[:8]
    data = _create(client, name=f"Archie {tag}")
    client.post(f"/patients/{data['id']}/archive")

    assert client.get("/patients", params={"q": tag}).json()["total"] == 0
    assert client.get(
        "/patients", params={"q": tag, "include_archived": "true"}
    ).json()["total"] == 1


def test_archived_patient_refuses_new_activity(as_staff):
    """An archived record is RETAINED but not actively added to (6.13).

    `patient_files.py` has enforced this since 5.6; booking and visits never got
    the same rule, so the API accepted activity the UI already hides. Making the
    three consistent is the point — the failure mode was a patient archived by
    mistake quietly accumulating new appointments.
    """
    client, _ = as_staff
    tag = uuid.uuid4().hex[:8]
    patient = _create(client, name=f"Gone {tag}")
    client.post(f"/patients/{patient['id']}/archive")

    booked = client.post(
        "/appointments",
        json={
            "patient_id": patient["id"],
            "start_time": "2099-01-01T10:00:00+00:00",
            "duration_min": 30,
        },
    )
    assert booked.status_code == 409, booked.text
    assert "archived" in booked.json()["detail"].lower()

    # Unarchiving must make it work again — this is a soft block, not a dead end.
    client.post(f"/patients/{patient['id']}/unarchive")
    again = client.post(
        "/appointments",
        json={
            "patient_id": patient["id"],
            "start_time": "2099-01-01T10:00:00+00:00",
            "duration_min": 30,
        },
    )
    assert again.status_code == 201, again.text


def test_pagination_and_limit_bounds(as_staff):
    client, _ = as_staff
    tag = uuid.uuid4().hex[:8]
    for i in range(3):
        _create(client, name=f"Page {tag} {i}")

    first = client.get("/patients", params={"q": tag, "limit": 2, "offset": 0}).json()
    assert first["total"] == 3
    assert len(first["items"]) == 2

    second = client.get("/patients", params={"q": tag, "limit": 2, "offset": 2}).json()
    assert len(second["items"]) == 1

    # limit above the cap is rejected by validation
    assert client.get("/patients", params={"limit": 999}).status_code == 422
