"""Endpoint tests for the treatment catalogue (step 4.1).

DB-backed, on the test_patients.py template (auth faked by overriding
get_current_claims; skips fast without a database).

This is the project's FIRST role-split resource, so the headline test is
`test_non_admin_cannot_write`: a receptionist can read the catalogue but is
rejected with 403 on every mutation. That proves require_role guards the API
itself, not just the UI.

Prices are Decimal end to end — the round-trip test asserts exact 2-dp values,
which is the whole reason default_price is Numeric and not a float.
"""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.auth import get_current_claims
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.staff_user import StaffUser
from app.models.treatment_item import TreatmentItem

client = TestClient(app)


def test_requires_auth():
    assert client.get("/treatment-items").status_code in (401, 403)
    assert client.post(
        "/treatment-items", json={"name": "X", "default_price": "10.00"}
    ).status_code in (401, 403)


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


_item_ids: list[uuid.UUID] = []


def _staff_fixture(roles: list[str]):
    """Build a TestClient acting as a staff member with the given roles."""
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name=f"Test {'/'.join(roles)}",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=roles,
        active=True,
    )
    db.add(staff)
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    return db, staff


def _cleanup(db, staff):
    app.dependency_overrides.clear()
    for iid in _item_ids:
        obj = db.get(TreatmentItem, iid)
        if obj is not None:
            db.delete(obj)
    for row in db.execute(
        select(AuditLog).where(AuditLog.actor_id == staff.id)
    ).scalars():
        db.delete(row)
    db.commit()
    _item_ids.clear()
    db.delete(db.get(StaffUser, staff.id))
    db.commit()
    db.close()


@pytest.fixture
def as_admin(db_available):
    db, staff = _staff_fixture(["admin"])
    try:
        yield client, staff.id
    finally:
        _cleanup(db, staff)


@pytest.fixture
def as_receptionist(db_available):
    db, staff = _staff_fixture(["receptionist"])
    try:
        yield client, staff.id
    finally:
        _cleanup(db, staff)


def _create(client: TestClient, name: str, price: str = "500.00"):
    resp = client.post(
        "/treatment-items", json={"name": name, "default_price": price}
    )
    if resp.status_code == 201:
        _item_ids.append(uuid.UUID(resp.json()["id"]))
    return resp


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


# --- the role split (the point of this step) ---------------------------------

def test_non_admin_cannot_write(as_receptionist):
    """A receptionist reads the catalogue fine but cannot change it."""
    client, _ = as_receptionist

    # Reading is allowed for any active staff.
    assert client.get("/treatment-items").status_code == 200

    # Every mutation is admin-only -> 403.
    assert _create(client, _unique("Sneaky")).status_code == 403
    assert client.patch(
        f"/treatment-items/{uuid.uuid4()}", json={"name": "Nope"}
    ).status_code == 403
    assert client.post(
        f"/treatment-items/{uuid.uuid4()}/deactivate"
    ).status_code == 403
    assert client.post(f"/treatment-items/{uuid.uuid4()}/activate").status_code == 403


# --- admin CRUD ---------------------------------------------------------------

def test_admin_create_and_audit(as_admin):
    client, staff_id = as_admin
    name = _unique("Cleaning")
    resp = _create(client, name, "1200.50")
    assert resp.status_code == 201, resp.text

    data = resp.json()
    assert data["name"] == name
    assert Decimal(str(data["default_price"])) == Decimal("1200.50")
    assert data["active"] is True

    db = SessionLocal()
    try:
        actions = {
            a.action
            for a in db.execute(
                select(AuditLog).where(
                    AuditLog.actor_id == staff_id,
                    AuditLog.entity_id == uuid.UUID(data["id"]),
                )
            ).scalars()
        }
    finally:
        db.close()
    assert "create" in actions


def test_duplicate_name_conflicts(as_admin):
    client, _ = as_admin
    name = _unique("Filling")
    assert _create(client, name).status_code == 201
    assert _create(client, name).status_code == 409


def test_price_roundtrips_exactly(as_admin):
    """Money is Numeric(10,2) — a price must come back exactly, not as a float."""
    client, _ = as_admin
    resp = _create(client, _unique("RCT"), "1999.99")
    assert Decimal(str(resp.json()["default_price"])) == Decimal("1999.99")

    item_id = resp.json()["id"]
    patched = client.patch(
        f"/treatment-items/{item_id}", json={"default_price": "2500.05"}
    )
    assert patched.status_code == 200
    assert Decimal(str(patched.json()["default_price"])) == Decimal("2500.05")


def test_patch_updates_only_given_fields(as_admin):
    client, _ = as_admin
    name = _unique("Extraction")
    item_id = _create(client, name, "800.00").json()["id"]

    resp = client.patch(f"/treatment-items/{item_id}", json={"default_price": "900.00"})
    assert resp.status_code == 200
    assert resp.json()["name"] == name  # untouched
    assert Decimal(str(resp.json()["default_price"])) == Decimal("900.00")


def test_get_and_404(as_admin):
    client, _ = as_admin
    item_id = _create(client, _unique("Scaling")).json()["id"]
    assert client.get(f"/treatment-items/{item_id}").status_code == 200
    assert client.get(f"/treatment-items/{uuid.uuid4()}").status_code == 404


# --- deactivate / activate (never delete) ------------------------------------

def test_deactivate_is_soft_and_hidden_from_default_list(as_admin):
    client, _ = as_admin
    name = _unique("Retired")
    item_id = _create(client, name).json()["id"]

    resp = client.post(f"/treatment-items/{item_id}/deactivate")
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # Hidden from the default list...
    names = {i["name"] for i in client.get("/treatment-items").json()["items"]}
    assert name not in names

    # ...but still listed with the flag, and still fetchable by id (not deleted).
    names_all = {
        i["name"]
        for i in client.get(
            "/treatment-items", params={"include_inactive": "true"}
        ).json()["items"]
    }
    assert name in names_all
    assert client.get(f"/treatment-items/{item_id}").status_code == 200

    # And it can come back.
    assert client.post(f"/treatment-items/{item_id}/activate").json()["active"] is True
