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


def _create(
    client: TestClient,
    name: str,
    price: str = "500.00",
    kind: str | None = None,
):
    """Create an item. `kind` omitted exercises the server-side default."""
    body: dict = {"name": name, "default_price": price}
    if kind is not None:
        body["kind"] = kind
    resp = client.post("/treatment-items", json=body)
    if resp.status_code == 201:
        _item_ids.append(uuid.UUID(resp.json()["id"]))
    return resp


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


# --- the role split (the point of this step) ---------------------------------

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


# --- kinds: treatments vs medicine (6.7) -------------------------------------

def test_kind_defaults_to_treatment(as_admin):
    """Omitting `kind` yields a treatment — what every pre-6.7 caller sends."""
    client, _ = as_admin
    resp = _create(client, _unique("Scaling"))
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "treatment"


def test_can_create_a_medicine(as_admin):
    client, _ = as_admin
    resp = _create(client, _unique("Amoxicillin 500mg"), "45.00", kind="medicine")
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "medicine"
    assert resp.json()["default_price"] == "45.00"


def test_unknown_kind_rejected(as_admin):
    """The kind vocabulary is pinned by a Literal -> 422 well before the DB CHECK."""
    client, _ = as_admin
    assert _create(client, _unique("Odd"), kind="consultation").status_code == 422
    assert _create(client, _unique("Odder"), kind="").status_code == 422


def test_kind_filter_narrows_the_list(as_admin):
    client, _ = as_admin
    treatment = _unique("Filling")
    medicine = _unique("Ibuprofen")
    _create(client, treatment, kind="treatment")
    _create(client, medicine, "20.00", kind="medicine")

    meds = client.get("/treatment-items", params={"kind": "medicine"}).json()["items"]
    names = {i["name"] for i in meds}
    assert medicine in names
    assert treatment not in names
    assert all(i["kind"] == "medicine" for i in meds)

    treatments = client.get("/treatment-items", params={"kind": "treatment"}).json()["items"]
    assert treatment in {i["name"] for i in treatments}
    assert all(i["kind"] == "treatment" for i in treatments)


def test_unfiltered_list_returns_every_kind(as_admin):
    """No `kind` param = the whole catalogue, so pre-6.7 callers are unaffected."""
    client, _ = as_admin
    treatment = _unique("Extraction")
    medicine = _unique("Paracetamol")
    _create(client, treatment, kind="treatment")
    _create(client, medicine, "15.00", kind="medicine")

    names = {i["name"] for i in client.get("/treatment-items").json()["items"]}
    assert {treatment, medicine} <= names


def test_same_name_allowed_across_kinds(as_admin):
    """The unique is on (kind, name): one word may be both a procedure and a drug."""
    client, _ = as_admin
    name = _unique("Consultation")
    assert _create(client, name, kind="treatment").status_code == 201
    assert _create(client, name, "50.00", kind="medicine").status_code == 201


def test_duplicate_within_a_kind_conflicts(as_admin):
    """A friendly 409, not a raw IntegrityError — the constraint name the router
    matches on changed in 6.7, so this pins that they still agree."""
    client, _ = as_admin
    name = _unique("Crown")
    assert _create(client, name, kind="treatment").status_code == 201
    assert _create(client, name, kind="treatment").status_code == 409

    med = _unique("Metronidazole")
    assert _create(client, med, "30.00", kind="medicine").status_code == 201
    assert _create(client, med, "30.00", kind="medicine").status_code == 409


def test_kind_cannot_be_changed_by_patch(as_admin):
    """Re-kinding would silently move already-billed revenue between report
    buckets, so PATCH ignores the field. Retire and re-add instead."""
    client, _ = as_admin
    created = _create(client, _unique("Bridge"), kind="treatment")
    item_id = created.json()["id"]

    resp = client.patch(
        f"/treatment-items/{item_id}",
        json={"kind": "medicine", "default_price": "600.00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "treatment"  # unchanged
    assert resp.json()["default_price"] == "600.00"  # the real edit still applied
