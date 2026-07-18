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
