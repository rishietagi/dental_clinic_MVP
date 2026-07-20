"""Endpoint tests for visit recording (step 4.3).

DB-backed, on the test_treatment_items.py template (auth faked by overriding
get_current_claims; skips fast without a database).

The headline tests are the ones that pin BUILD_PLAN §3's promise into behaviour:

- `test_single_visit_work_auto_creates_and_closes` — the "cleaning — done" case.
  One request, no treatment_id, and the treatment comes back created AND closed,
  so it never lingers on the 4.8 open-treatments report.
- `test_second_sitting_continues_the_thread` — the RCT case. Two visits, one
  treatment, still open.
- `test_unknown_item_writes_nothing` — the transactional guarantee: a bad
  procedure id must leave no half-written visit behind.
- `test_receptionist_cannot_record_visits` — the role split lives on the API.

Cleanup runs child-first (procedures -> visits -> treatments -> patients) and
commits per delete, because SQLAlchemy reorders a batched flush and trips the FKs.
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
from app.models.audit_log import AuditLog
from app.models.patient import Patient
from app.models.procedure_performed import ProcedurePerformed
from app.models.staff_user import StaffUser
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit

client = TestClient(app)


def test_requires_auth():
    assert client.get("/visits?patient_id=" + str(uuid.uuid4())).status_code in (401, 403)
    assert client.post("/visits", json={}).status_code in (401, 403)


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


class Ctx:
    """Everything a test needs: the client, the acting staff, a patient, an item."""

    def __init__(self, db, staff, patient, item):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.item = item
        self.client = client


def _make_ctx(roles: list[str]) -> Ctx:
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name=f"Test {'/'.join(roles)}",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=roles,
        active=True,
    )
    patient = Patient(name="Visit Test Patient")
    item = TreatmentItem(
        name=f"Test Item {uuid.uuid4().hex[:8]}", default_price="500.00"
    )
    db.add_all([staff, patient, item])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}
    return Ctx(db, staff, patient, item)


def _cleanup(ctx: Ctx) -> None:
    app.dependency_overrides.clear()
    db = ctx.db
    db.rollback()

    # Child-first, committing each delete so the order is the one Postgres sees.
    patient_ids = [ctx.patient.id]
    visit_ids = [
        v.id for v in db.scalars(
            select(Visit).where(Visit.patient_id.in_(patient_ids))
        )
    ]
    for vid in visit_ids:
        for proc in db.scalars(
            select(ProcedurePerformed).where(ProcedurePerformed.visit_id == vid)
        ):
            db.delete(proc)
            db.commit()
        db.delete(db.get(Visit, vid))
        db.commit()
    for t in db.scalars(select(Treatment).where(Treatment.patient_id.in_(patient_ids))):
        db.delete(t)
        db.commit()
    for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == ctx.staff.id)):
        db.delete(row)
        db.commit()
    for model, oid in [
        (TreatmentItem, ctx.item.id),
        (Patient, ctx.patient.id),
        (StaffUser, ctx.staff.id),
    ]:
        obj = db.get(model, oid)
        if obj is not None:
            db.delete(obj)
            db.commit()
    db.close()


@pytest.fixture
def as_dentist(db_available):
    ctx = _make_ctx(["dentist"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


@pytest.fixture
def as_receptionist(db_available):
    ctx = _make_ctx(["receptionist"])
    try:
        yield ctx
    finally:
        _cleanup(ctx)


def _body(ctx: Ctx, **overrides) -> dict:
    body = {
        "patient_id": str(ctx.patient.id),
        "treatment": {"title": "RCT tooth 36", "tooth_ref": "36"},
        "clinical_notes": "access opening, temp filling",
    }
    body.update(overrides)
    return body


# --- the auto-create / auto-close rule ---------------------------------------

def test_new_work_auto_creates_a_treatment(as_dentist):
    ctx = as_dentist
    resp = ctx.client.post("/visits", json=_body(ctx))
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["treatment"]["title"] == "RCT tooth 36"
    assert data["treatment"]["tooth_ref"] == "36"
    assert data["treatment"]["status"] == "in_progress"
    assert data["treatment"]["closed_at"] is None
    assert data["treatment_id"] == data["treatment"]["id"]

    # It really exists in the DB, not just in the response.
    assert ctx.db.get(Treatment, uuid.UUID(data["treatment"]["id"])) is not None


def test_single_visit_work_auto_creates_and_closes(as_dentist):
    """The 'cleaning — done' case: one call, treatment created AND closed."""
    ctx = as_dentist
    resp = ctx.client.post(
        "/visits",
        json=_body(
            ctx,
            treatment={"title": "Cleaning", "tooth_ref": None},
            treatment_status="completed",
            clinical_notes="scaling, full mouth",
        ),
    )
    assert resp.status_code == 201, resp.text
    treatment = resp.json()["treatment"]

    assert treatment["status"] == "completed"
    assert treatment["closed_at"] is not None  # closed in the same request

    ctx.db.expire_all()
    row = ctx.db.get(Treatment, uuid.UUID(treatment["id"]))
    assert row.status == "completed"
    assert row.closed_at is not None


def test_second_sitting_continues_the_thread(as_dentist):
    """The RCT case: two visits, one treatment, still open."""
    ctx = as_dentist
    first = ctx.client.post("/visits", json=_body(ctx))
    assert first.status_code == 201
    treatment_id = first.json()["treatment_id"]

    second = ctx.client.post(
        "/visits",
        json={
            "patient_id": str(ctx.patient.id),
            "treatment_id": treatment_id,
            "clinical_notes": "cleaning & shaping",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["treatment_id"] == treatment_id

    # One treatment, two visits.
    listing = ctx.client.get(f"/visits?treatment_id={treatment_id}")
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert second.json()["treatment"]["status"] == "in_progress"


def test_closing_on_the_final_sitting(as_dentist):
    """Continuing a thread AND closing it in the same request."""
    ctx = as_dentist
    first = ctx.client.post("/visits", json=_body(ctx))
    treatment_id = first.json()["treatment_id"]

    final = ctx.client.post(
        "/visits",
        json={
            "patient_id": str(ctx.patient.id),
            "treatment_id": treatment_id,
            "clinical_notes": "obturation + crown",
            "treatment_status": "completed",
        },
    )
    assert final.status_code == 201
    assert final.json()["treatment"]["status"] == "completed"
    assert final.json()["treatment"]["closed_at"] is not None


# --- guards ------------------------------------------------------------------

def test_exactly_one_treatment_form_required(as_dentist):
    ctx = as_dentist
    # Neither.
    neither = ctx.client.post("/visits", json={"patient_id": str(ctx.patient.id)})
    assert neither.status_code == 422

    # Both.
    both = ctx.client.post(
        "/visits",
        json={
            "patient_id": str(ctx.patient.id),
            "treatment_id": str(uuid.uuid4()),
            "treatment": {"title": "X"},
        },
    )
    assert both.status_code == 422


def test_unknown_treatment_is_404(as_dentist):
    ctx = as_dentist
    resp = ctx.client.post(
        "/visits",
        json={"patient_id": str(ctx.patient.id), "treatment_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


def test_treatment_from_another_patient_is_409(as_dentist):
    """A visit must not splice two patients' histories together."""
    ctx = as_dentist
    other = Patient(name="Other Patient")
    ctx.db.add(other)
    ctx.db.commit()
    other_treatment = Treatment(patient_id=other.id, title="Someone else's RCT")
    ctx.db.add(other_treatment)
    ctx.db.commit()

    try:
        resp = ctx.client.post(
            "/visits",
            json={
                "patient_id": str(ctx.patient.id),
                "treatment_id": str(other_treatment.id),
            },
        )
        assert resp.status_code == 409
    finally:
        ctx.db.delete(ctx.db.get(Treatment, other_treatment.id))
        ctx.db.commit()
        ctx.db.delete(ctx.db.get(Patient, other.id))
        ctx.db.commit()


def test_cannot_add_a_visit_to_a_completed_treatment(as_dentist):
    ctx = as_dentist
    first = ctx.client.post(
        "/visits", json=_body(ctx, treatment_status="completed")
    )
    treatment_id = first.json()["treatment_id"]

    resp = ctx.client.post(
        "/visits",
        json={"patient_id": str(ctx.patient.id), "treatment_id": treatment_id},
    )
    assert resp.status_code == 409


def test_unknown_treatment_status_is_422(as_dentist):
    ctx = as_dentist
    resp = ctx.client.post("/visits", json=_body(ctx, treatment_status="finished"))
    assert resp.status_code == 422


def test_unknown_item_writes_nothing(as_dentist):
    """The transactional guarantee: a bad procedure id leaves no partial visit."""
    ctx = as_dentist
    before = ctx.db.scalar(
        select(Visit).where(Visit.patient_id == ctx.patient.id)
    )
    assert before is None

    resp = ctx.client.post(
        "/visits",
        json=_body(
            ctx,
            procedures=[{"treatment_item_id": str(uuid.uuid4()), "tooth_ref": "36"}],
        ),
    )
    assert resp.status_code == 404

    ctx.db.expire_all()
    # No visit, and no orphan treatment either.
    assert ctx.db.scalar(select(Visit).where(Visit.patient_id == ctx.patient.id)) is None
    assert (
        ctx.db.scalar(select(Treatment).where(Treatment.patient_id == ctx.patient.id))
        is None
    )


# --- the role split ----------------------------------------------------------

def test_receptionist_cannot_record_visits(as_receptionist):
    """Reads yes, writes no — enforced on the API, not just hidden in the UI."""
    ctx = as_receptionist

    # A visit to read, created directly (the API would reject this role).
    treatment = Treatment(patient_id=ctx.patient.id, title="Existing")
    ctx.db.add(treatment)
    ctx.db.commit()
    visit = Visit(patient_id=ctx.patient.id, treatment_id=treatment.id)
    ctx.db.add(visit)
    ctx.db.commit()

    assert ctx.client.get(f"/visits/{visit.id}").status_code == 200
    assert ctx.client.get(f"/visits?patient_id={ctx.patient.id}").status_code == 200

    assert ctx.client.post("/visits", json=_body(ctx)).status_code == 403
    assert ctx.client.patch(
        f"/visits/{visit.id}", json={"clinical_notes": "nope"}
    ).status_code == 403


# --- procedures, reads, updates ----------------------------------------------

def test_procedures_round_trip_with_names(as_dentist):
    ctx = as_dentist
    resp = ctx.client.post(
        "/visits",
        json=_body(
            ctx,
            procedures=[
                {"treatment_item_id": str(ctx.item.id), "tooth_ref": "36"},
                {"treatment_item_id": str(ctx.item.id), "tooth_ref": None},
            ],
        ),
    )
    assert resp.status_code == 201, resp.text
    procs = resp.json()["procedures"]
    assert len(procs) == 2
    assert {p["treatment_item_name"] for p in procs} == {ctx.item.name}
    assert {p["tooth_ref"] for p in procs} == {"36", None}


def test_get_visit_and_404(as_dentist):
    ctx = as_dentist
    created = ctx.client.post("/visits", json=_body(ctx)).json()

    got = ctx.client.get(f"/visits/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]
    assert got.json()["treatment"]["title"] == "RCT tooth 36"

    assert ctx.client.get(f"/visits/{uuid.uuid4()}").status_code == 404


def test_list_requires_exactly_one_filter(as_dentist):
    ctx = as_dentist
    assert ctx.client.get("/visits").status_code == 422
    assert ctx.client.get(
        f"/visits?patient_id={ctx.patient.id}&treatment_id={uuid.uuid4()}"
    ).status_code == 422


def test_patch_updates_notes_only(as_dentist):
    ctx = as_dentist
    created = ctx.client.post("/visits", json=_body(ctx)).json()

    resp = ctx.client.patch(
        f"/visits/{created['id']}", json={"clinical_notes": "corrected note"}
    )
    assert resp.status_code == 200
    assert resp.json()["clinical_notes"] == "corrected note"
    # Untouched fields survive.
    assert resp.json()["treatment_id"] == created["treatment_id"]
    assert resp.json()["complaint"] == created["complaint"]

    assert ctx.client.patch(
        f"/visits/{uuid.uuid4()}", json={"clinical_notes": "x"}
    ).status_code == 404


def test_visit_defaults_dentist_to_the_recorder(as_dentist):
    """An omitted dentist_id means 'the dentist recording it'."""
    ctx = as_dentist
    data = ctx.client.post("/visits", json=_body(ctx)).json()
    assert data["dentist_id"] == str(ctx.staff.id)


def test_explicit_visit_date_is_kept(as_dentist):
    ctx = as_dentist
    when = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    data = ctx.client.post(
        "/visits", json=_body(ctx, visit_date=when.isoformat())
    ).json()
    assert data["visit_date"].startswith("2026-08-02T10:00")


def test_creating_a_visit_writes_audit_rows(as_dentist):
    """Both the visit AND the auto-created treatment are auditable."""
    ctx = as_dentist
    data = ctx.client.post("/visits", json=_body(ctx)).json()

    rows = list(
        ctx.db.scalars(select(AuditLog).where(AuditLog.actor_id == ctx.staff.id))
    )
    entities = {(r.entity, str(r.entity_id)) for r in rows}
    assert ("visit", data["id"]) in entities
    assert ("treatment", data["treatment_id"]) in entities

    treatment_row = next(r for r in rows if r.entity == "treatment")
    assert treatment_row.details["auto_created_by_visit"] is True
