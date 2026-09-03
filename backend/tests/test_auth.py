"""Tests for staff identity — there is no authentication since 10.1.

The app is a single-user desktop app: `get_current_claims` names the one local
staff row instead of verifying a token, and `require_role` always passes. What
still matters, and what these tests pin:

  - `/me` resolves a REAL staff_user row, so everything attributed to staff
    (audit_log.actor_id, visit.dentist_id, by-dentist reporting) keeps working.
  - a previously role-gated endpoint is now reachable by anyone.
  - a MISSING or DEACTIVATED local staff row fails loud (500) rather than
    silently writing audit rows that point at nobody.

Removed with authentication: the "no token -> 401" tests, and every
receptionist/dentist-is-forbidden test from 6.12. Skips if no database.
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


# --- staff identity ----------------------------------------------------------

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
    """Act as this staff row (the seam every suite uses instead of a login)."""
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


def test_admin_ping_allows_admin(staff_factory):
    admin = staff_factory(["dentist", "admin"])
    _override_claims(str(admin.id))
    assert client.get("/admin/ping").status_code == 200


def test_role_gate_is_a_no_op_now(staff_factory):
    """A receptionist reaches a formerly admin-only endpoint (10.1).

    This is the behaviour change made deliberately: `require_role` still wraps
    the endpoint and still documents that it WAS privileged, but with one user
    on one machine there is nobody to refuse. If real roles are ever restored,
    this test is the one that should start failing.
    """
    reception = staff_factory(["receptionist"])
    _override_claims(str(reception.id))
    assert client.get("/admin/ping").status_code == 200


def test_missing_local_staff_row_fails_loud(db_available):
    """A misconfigured install must not silently proceed.

    If the seed never ran, writes would attribute to a staff member who does not
    exist. Better a 500 naming the fix than an audit trail pointing at nobody.
    """
    _override_claims(str(uuid.uuid4()))  # nothing with this id exists
    resp = client.get("/me")
    assert resp.status_code == 500
    assert "seed" in resp.json()["detail"].lower()


def test_deactivated_local_staff_fails_loud(staff_factory):
    """Same for a deactivated row — the app is unusable, and says so."""
    who = staff_factory(["dentist", "admin"], active=False)
    _override_claims(str(who.id))
    resp = client.get("/me")
    assert resp.status_code == 500
    assert "seed" in resp.json()["detail"].lower()


