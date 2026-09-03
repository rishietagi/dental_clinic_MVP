"""Endpoint tests for the staff directory + management (6.3 reads, 6.5 writes).

DB-backed, auth faked by overriding get_current_claims. `GET /staff` powers the
dentist dropdowns; the writes let an admin register/deactivate name-only dentist
records. Reads = any active staff; writes = admin only.
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
from app.models.staff_user import StaffUser

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


@pytest.fixture
def env(db_available):
    """Admin + receptionist actors, plus a dentist and an inactive staff row.

    Yields (client, ids) where ids has admin/recep/dentist/inactive + act_as(); the
    default actor is the admin (for the write tests). Created rows are tracked +
    cleaned up.
    """
    db = SessionLocal()
    created: list[uuid.UUID] = []

    admin = StaffUser(id=uuid.uuid4(), name="Admin", email=f"{uuid.uuid4()}@clinic.local", roles=["admin"], active=True)
    recep = StaffUser(id=uuid.uuid4(), name="Recep", email=f"{uuid.uuid4()}@clinic.local", roles=["receptionist"], active=True)
    dentist = StaffUser(id=uuid.uuid4(), name="ZZZ Dr Filter", email=f"{uuid.uuid4()}@clinic.local", roles=["dentist"], active=True)
    inactive = StaffUser(id=uuid.uuid4(), name="Inactive Dr", email=f"{uuid.uuid4()}@clinic.local", roles=["dentist"], active=False)
    db.add_all([admin, recep, dentist, inactive])
    db.commit()

    def act_as(who: StaffUser):
        app.dependency_overrides[get_current_claims] = lambda: {"sub": str(who.id)}

    act_as(admin)

    ns = {
        "admin": admin, "recep": recep, "dentist_id": dentist.id, "inactive_id": inactive.id,
        "act_as": act_as, "created": created,
    }
    try:
        yield client, ns
    finally:
        app.dependency_overrides.clear()
        # Remove any staff the tests created + audit rows the admin produced.
        for cid in created:
            obj = db.get(StaffUser, cid)
            if obj is not None:
                db.delete(obj)
            db.commit()
        for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == admin.id)):
            db.delete(row)
        db.commit()
        for s in (admin, recep, dentist, inactive):
            obj = db.get(StaffUser, s.id)
            if obj is not None:
                db.delete(obj)
            db.commit()
        db.close()


# --- reads -------------------------------------------------------------------

def test_lists_active_staff(env):
    client, ns = env
    data = client.get("/staff").json()
    ids = {i["id"] for i in data["items"]}
    assert str(ns["dentist_id"]) in ids
    assert str(ns["inactive_id"]) not in ids  # inactive excluded by default
    row = next(i for i in data["items"] if i["id"] == str(ns["dentist_id"]))
    # Pinned so a new column can't leak out of the model by accident.
    # `consultation_fee` joined the summary deliberately in 6.7 — the Pricing
    # screen and the visit form both read it from here.
    assert set(row.keys()) == {
        "id",
        "name",
        "email",
        "roles",
        "active",
        "consultation_fee",
    }


def test_include_inactive(env):
    client, ns = env
    data = client.get("/staff", params={"include_inactive": "true"}).json()
    assert str(ns["inactive_id"]) in {i["id"] for i in data["items"]}


def test_filters_by_role(env):
    client, ns = env
    data = client.get("/staff", params={"role": "dentist"}).json()
    assert all("dentist" in i["roles"] for i in data["items"])
    assert str(ns["dentist_id"]) in {i["id"] for i in data["items"]}


# --- writes (6.5) ------------------------------------------------------------

def test_admin_creates_dentist(env):
    client, ns = env
    email = f"{uuid.uuid4()}@clinic.local"
    resp = client.post("/staff", json={"name": "Dr. New Person", "email": email})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    ns["created"].append(uuid.UUID(data["id"]))
    assert data["name"] == "Dr. New Person"
    assert data["roles"] == ["dentist"]  # default
    assert data["active"] is True
    # Appears in the dentist dropdown query.
    dentists = client.get("/staff", params={"role": "dentist"}).json()["items"]
    assert data["id"] in {i["id"] for i in dentists}


def test_duplicate_email_conflicts(env):
    client, ns = env
    email = f"{uuid.uuid4()}@clinic.local"
    first = client.post("/staff", json={"name": "A", "email": email})
    assert first.status_code == 201
    ns["created"].append(uuid.UUID(first.json()["id"]))
    dup = client.post("/staff", json={"name": "B", "email": email})
    assert dup.status_code == 409


def test_deactivate_hides_from_dropdown(env):
    client, ns = env
    created = client.post("/staff", json={"name": "Dr. Temp", "email": f"{uuid.uuid4()}@clinic.local"})
    sid = created.json()["id"]
    ns["created"].append(uuid.UUID(sid))

    off = client.post(f"/staff/{sid}/deactivate")
    assert off.status_code == 200
    assert off.json()["active"] is False
    # Gone from the default dentist list, back with include_inactive.
    assert sid not in {i["id"] for i in client.get("/staff", params={"role": "dentist"}).json()["items"]}
    assert sid in {i["id"] for i in client.get("/staff", params={"include_inactive": "true"}).json()["items"]}

    on = client.post(f"/staff/{sid}/activate")
    assert on.status_code == 200
    assert on.json()["active"] is True
    assert sid in {i["id"] for i in client.get("/staff", params={"role": "dentist"}).json()["items"]}


# --- consultation fee (6.7) --------------------------------------------------

def _make_dentist(client, ns, **extra) -> str:
    """Create a dentist and register it for cleanup; returns its id."""
    body = {"name": "Dr. Fee", "email": f"{uuid.uuid4()}@clinic.local", **extra}
    resp = client.post("/staff", json=body)
    assert resp.status_code == 201, resp.text
    sid = resp.json()["id"]
    ns["created"].append(uuid.UUID(sid))
    return sid


def test_fee_defaults_to_unset(env):
    """No fee given -> null, NOT 0. The visit screen offers nothing until it's set."""
    client, ns = env
    sid = _make_dentist(client, ns)
    row = next(
        i for i in client.get("/staff").json()["items"] if i["id"] == sid
    )
    assert row["consultation_fee"] is None


def test_admin_sets_fee(env):
    client, ns = env
    sid = _make_dentist(client, ns)

    resp = client.patch(f"/staff/{sid}", json={"consultation_fee": "300.00"})
    assert resp.status_code == 200, resp.text
    # Money crosses the wire as a string so the exact decimal survives.
    assert resp.json()["consultation_fee"] == "300.00"

    # And it is readable from the list the Pricing screen + visit form use.
    row = next(i for i in client.get("/staff").json()["items"] if i["id"] == sid)
    assert row["consultation_fee"] == "300.00"


def test_fee_can_be_set_at_creation(env):
    client, ns = env
    sid = _make_dentist(client, ns, consultation_fee="450.50")
    row = next(i for i in client.get("/staff").json()["items"] if i["id"] == sid)
    assert row["consultation_fee"] == "450.50"


def test_explicit_null_clears_the_fee(env):
    """Sending null CLEARS it — distinct from omitting the field entirely."""
    client, ns = env
    sid = _make_dentist(client, ns, consultation_fee="300.00")

    cleared = client.patch(f"/staff/{sid}", json={"consultation_fee": None})
    assert cleared.status_code == 200
    assert cleared.json()["consultation_fee"] is None


def test_omitted_field_leaves_fee_untouched(env):
    """A PATCH that only renames must not wipe the fee (the exclude_unset rule)."""
    client, ns = env
    sid = _make_dentist(client, ns, consultation_fee="300.00")

    renamed = client.patch(f"/staff/{sid}", json={"name": "Dr. Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Dr. Renamed"
    assert renamed.json()["consultation_fee"] == "300.00"


def test_zero_fee_is_allowed_and_distinct_from_unset(env):
    """0.00 means 'charges nothing' — a real answer, not the absence of one."""
    client, ns = env
    sid = _make_dentist(client, ns)
    resp = client.patch(f"/staff/{sid}", json={"consultation_fee": "0.00"})
    assert resp.status_code == 200
    assert resp.json()["consultation_fee"] == "0.00"


def test_negative_fee_rejected(env):
    client, ns = env
    sid = _make_dentist(client, ns)
    assert client.patch(f"/staff/{sid}", json={"consultation_fee": "-10.00"}).status_code == 422


def test_patch_unknown_staff_404(env):
    client, ns = env
    resp = client.patch(f"/staff/{uuid.uuid4()}", json={"consultation_fee": "100.00"})
    assert resp.status_code == 404


def test_patch_does_not_shadow_deactivate_route(env):
    """`PATCH /staff/{id}` must not swallow `/staff/{id}/deactivate` (the
    literal-before-{id} family of bugs). Both still work."""
    client, ns = env
    sid = _make_dentist(client, ns)
    assert client.patch(f"/staff/{sid}", json={"consultation_fee": "100.00"}).status_code == 200
    assert client.post(f"/staff/{sid}/deactivate").status_code == 200
