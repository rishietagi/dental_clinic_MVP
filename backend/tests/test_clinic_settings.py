"""Endpoint tests for clinic settings (step 4.9).

DB-backed, on the test_treatment_items.py template (auth faked by overriding
get_current_claims; skips fast without a database).

`clinic_settings` is a SINGLETON row seeded by the migration, so unlike other
suites these tests don't create/delete rows — they read and PATCH the one row,
and the fixture snapshots + restores it so a mutation doesn't bleed into other
tests (the appointments IST test reads the same timezone).

Role split like the catalogue: any staff GET, admin-only PATCH.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings as app_settings
from app.db import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.clinic_settings import ClinicSettings
from app.models.staff_user import StaffUser

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


def _staff(roles: list[str]) -> StaffUser:
    db = SessionLocal()
    s = StaffUser(
        id=uuid.uuid4(),
        name=f"Test {'/'.join(roles)}",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=roles,
        active=True,
    )
    db.add(s)
    db.commit()
    db.close()
    return s


@pytest.fixture
def env(db_available):
    """Yields (client, admin_id, act_as). Snapshots the settings row and any test
    staff, and restores everything afterwards."""
    db = SessionLocal()
    admin = _staff(["admin"])
    recep = _staff(["receptionist"])

    def act_as(staff: StaffUser):
        app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}

    def reset_to_seed():
        # Restore the singleton to the migration's seeded defaults. Fixed values
        # (not a snapshot) so a test that fails mid-PATCH can't leave the row
        # drifted for the next test. Both setup and teardown call this.
        db.expire_all()
        r = db.get(ClinicSettings, 1)
        r.open_hour, r.close_hour, r.slot_minutes, r.timezone = 9, 18, 30, "Asia/Kolkata"
        r.clinic_name, r.address, r.phone = "Dental Clinic", None, None
        db.commit()

    reset_to_seed()
    act_as(admin)
    try:
        yield client, admin, recep, act_as
    finally:
        app.dependency_overrides.clear()
        reset_to_seed()
        # Remove test staff + their audit rows.
        for s in (admin, recep):
            for al in db.scalars(select(AuditLog).where(AuditLog.actor_id == s.id)):
                db.delete(al)
            db.commit()
            obj = db.get(StaffUser, s.id)
            if obj is not None:
                db.delete(obj)
            db.commit()
        db.close()


def test_get_returns_the_seeded_defaults(env):
    client, _admin, _recep, _ = env
    resp = client.get("/clinic-settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 1
    assert data["open_hour"] == 9
    assert data["close_hour"] == 18
    assert data["slot_minutes"] == 30
    assert data["timezone"] == "Asia/Kolkata"


def test_admin_can_patch(env):
    client, _admin, _recep, _ = env
    resp = client.patch(
        "/clinic-settings",
        json={"open_hour": 8, "close_hour": 20, "slot_minutes": 15, "timezone": "UTC"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["open_hour"], data["close_hour"], data["slot_minutes"], data["timezone"]) == (
        8, 20, 15, "UTC",
    )
    # Persisted.
    assert client.get("/clinic-settings").json()["open_hour"] == 8


def test_invalid_timezone_is_422(env):
    client, _admin, _recep, _ = env
    assert client.patch(
        "/clinic-settings", json={"timezone": "Mars/Olympus"}
    ).status_code == 422


def test_close_not_after_open_is_422(env):
    client, _admin, _recep, _ = env
    # Directly invalid (both in one PATCH).
    assert client.patch(
        "/clinic-settings", json={"open_hour": 10, "close_hour": 10}
    ).status_code == 422

    # Cross-field against the MERGED row: set a known close, then try to move open
    # to meet it. Don't rely on the seeded default (other tests may have run).
    assert client.patch("/clinic-settings", json={"close_hour": 17}).status_code == 200
    assert client.patch(
        "/clinic-settings", json={"open_hour": 17}
    ).status_code == 422


def test_out_of_range_hours_are_422(env):
    client, _admin, _recep, _ = env
    assert client.patch("/clinic-settings", json={"open_hour": 24}).status_code == 422
    assert client.patch("/clinic-settings", json={"slot_minutes": 0}).status_code == 422


def test_patch_is_audited(env):
    client, admin, _recep, _ = env
    client.patch("/clinic-settings", json={"open_hour": 10})

    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.actor_id == admin.id)
                .where(AuditLog.entity == "clinic_settings")
            )
        )
        assert any(r.action == "update" and r.details == {"open_hour": 10} for r in rows)
    finally:
        db.close()


def test_empty_patch_is_a_noop(env):
    client, _admin, _recep, _ = env
    before = client.get("/clinic-settings").json()
    resp = client.patch("/clinic-settings", json={})
    assert resp.status_code == 200
    assert resp.json()["open_hour"] == before["open_hour"]


# --- clinic identity fields (5.4) --------------------------------------------

def test_get_returns_identity_fields(env):
    client, _admin, _recep, _ = env
    data = client.get("/clinic-settings").json()
    assert data["clinic_name"] == "Dental Clinic"  # seeded default
    assert data["address"] is None
    assert data["phone"] is None


def test_admin_can_patch_identity(env):
    client, _admin, _recep, _ = env
    resp = client.patch(
        "/clinic-settings",
        json={
            "clinic_name": "Sri Dental Care",
            "address": "12 MG Road, Davangere",
            "phone": "+91 90000 00000",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["clinic_name"] == "Sri Dental Care"
    assert data["address"] == "12 MG Road, Davangere"
    assert data["phone"] == "+91 90000 00000"
    # Persisted.
    assert client.get("/clinic-settings").json()["clinic_name"] == "Sri Dental Care"


def test_blank_clinic_name_is_422(env):
    client, _admin, _recep, _ = env
    assert client.patch(
        "/clinic-settings", json={"clinic_name": ""}
    ).status_code == 422


