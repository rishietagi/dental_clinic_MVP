"""Endpoint tests for the staff directory (step 6.3).

DB-backed, auth faked by overriding get_current_claims. `GET /staff` powers the
dentist dropdowns on the booking + visit screens; it lists active staff, optionally
filtered by role, and never leaks more than id/name/roles.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.staff_user import StaffUser

client = TestClient(app)


def test_requires_auth():
    assert client.get("/staff").status_code in (401, 403)


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
def env(db_available):
    """A signed-in reader plus a dentist and an inactive staff row to filter on."""
    db = SessionLocal()
    reader = StaffUser(
        id=uuid.uuid4(), name="AAA Reader", email=f"{uuid.uuid4()}@clinic.local",
        roles=["receptionist"], active=True,
    )
    dentist = StaffUser(
        id=uuid.uuid4(), name="ZZZ Dr Filter", email=f"{uuid.uuid4()}@clinic.local",
        roles=["dentist"], active=True,
    )
    inactive = StaffUser(
        id=uuid.uuid4(), name="Inactive Dr", email=f"{uuid.uuid4()}@clinic.local",
        roles=["dentist"], active=False,
    )
    db.add_all([reader, dentist, inactive])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(reader.id)}
    try:
        yield client, dentist.id, inactive.id
    finally:
        app.dependency_overrides.clear()
        for s in (reader, dentist, inactive):
            obj = db.get(StaffUser, s.id)
            if obj is not None:
                db.delete(obj)
            db.commit()
        db.close()


def test_lists_active_staff(env):
    client, dentist_id, inactive_id = env
    data = client.get("/staff").json()
    ids = {i["id"] for i in data["items"]}
    assert str(dentist_id) in ids
    assert str(inactive_id) not in ids  # inactive excluded
    # Shape is minimal — no email leaked.
    row = next(i for i in data["items"] if i["id"] == str(dentist_id))
    assert set(row.keys()) == {"id", "name", "roles"}


def test_filters_by_role(env):
    client, dentist_id, _inactive = env
    data = client.get("/staff", params={"role": "dentist"}).json()
    assert all("dentist" in i["roles"] for i in data["items"])
    assert str(dentist_id) in {i["id"] for i in data["items"]}
