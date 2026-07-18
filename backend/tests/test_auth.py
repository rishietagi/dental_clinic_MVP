"""Tests for the auth dependencies and role-guarded endpoints.

Two layers:
  - DB-free: no bearer token -> 401. Always runs.
  - DB-backed: the role/lookup logic. We override get_current_claims to return a
    fake claims dict, so we test OUR code (staff lookup + role check) WITHOUT
    minting a real ES256 token. The signature-verification path (PyJWT + JWKS) is
    proven live against Supabase, not here. Skips if no database is reachable.
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


# --- DB-free: authentication is required -------------------------------------

def test_me_requires_token():
    assert client.get("/me").status_code in (401, 403)


def test_admin_ping_requires_token():
    assert client.get("/admin/ping").status_code in (401, 403)


# --- DB-backed: authorization logic ------------------------------------------

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
def staff_factory(db_available):
    """Create staff_user rows and clean them up afterwards."""
    created: list[uuid.UUID] = []
    db = SessionLocal()

    def make(roles: list[str], active: bool = True) -> StaffUser:
        sid = uuid.uuid4()
        staff = StaffUser(
            id=sid,
            name="Test Staff",
            email=f"{sid}@clinic.local",
            roles=roles,
            active=active,
        )
        db.add(staff)
        db.commit()
        created.append(sid)
        return staff

    try:
        yield make
    finally:
        for sid in created:
            obj = db.get(StaffUser, sid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        db.close()


def _override_claims(sub: str):
    """Make the auth chain believe a token with this `sub` was verified."""
    app.dependency_overrides[get_current_claims] = lambda: {"sub": sub}


def teardown_function():
    app.dependency_overrides.clear()


def test_me_returns_staff_and_roles(staff_factory):
    admin = staff_factory(["dentist", "admin"])
    _override_claims(str(admin.id))

    resp = client.get("/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == admin.email
    assert set(body["roles"]) == {"dentist", "admin"}
    assert body["active"] is True


def test_authenticated_but_no_staff_row_is_forbidden(db_available):
    _override_claims(str(uuid.uuid4()))  # a valid sub with no staff_user row
    assert client.get("/me").status_code == 403


def test_inactive_staff_is_forbidden(staff_factory):
    inactive = staff_factory(["receptionist"], active=False)
    _override_claims(str(inactive.id))
    assert client.get("/me").status_code == 403


def test_admin_ping_allows_admin(staff_factory):
    admin = staff_factory(["dentist", "admin"])
    _override_claims(str(admin.id))
    assert client.get("/admin/ping").status_code == 200


def test_admin_ping_forbids_non_admin(staff_factory):
    receptionist = staff_factory(["receptionist"])
    _override_claims(str(receptionist.id))
    assert client.get("/admin/ping").status_code == 403
    # but /me still works for them
    assert client.get("/me").status_code == 200
