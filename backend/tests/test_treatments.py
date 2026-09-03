"""Endpoint tests for the treatment read API (step 4.4).

DB-backed, on the test_visits.py template (auth faked by overriding
get_current_claims; skips fast without a database).

Read-only endpoints, so these are mostly about the query behaving: scoped to one
patient, the optional status filter, and the ordering the visit form relies on
(open treatments first, so "continue this thread" is at the top of the picker).

There are deliberately NO write tests — treatments are created by POST /visits
(4.3) and their lifecycle is 4.5. `test_no_write_routes` pins that down so
adding one is a conscious act rather than an accident.
"""

import uuid
from datetime import datetime, timedelta, timezone

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
from app.models.treatment import Treatment
from app.models.visit import Visit

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


class Ctx:
    def __init__(self, db, staff, patient, other_patient):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.other_patient = other_patient
        self.client = client


@pytest.fixture
def ctx(db_available):
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name="Test Dentist",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=["dentist"],
        active=True,
    )
    patient = Patient(name="Treatments Test Patient")
    other = Patient(name="Other Patient")
    db.add_all([staff, patient, other])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}

    c = Ctx(db, staff, patient, other)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        db.rollback()
        # Lifecycle tests (4.5) write audit rows keyed to the acting dentist.
        for row in list(
            db.scalars(select(AuditLog).where(AuditLog.actor_id == staff.id))
        ):
            db.delete(row)
            db.commit()
        # FK order: visits + appointments reference treatments, so delete them
        # first (4.8 flag tests create both).
        for pid in (patient.id, other.id):
            for v in list(db.scalars(select(Visit).where(Visit.patient_id == pid))):
                db.delete(v)
                db.commit()
            for a in list(
                db.scalars(select(Appointment).where(Appointment.patient_id == pid))
            ):
                db.delete(a)
                db.commit()
        for pid in (patient.id, other.id):
            for t in list(
                db.scalars(select(Treatment).where(Treatment.patient_id == pid))
            ):
                db.delete(t)
                db.commit()
        for model, oid in [
            (Patient, patient.id),
            (Patient, other.id),
            (StaffUser, staff.id),
        ]:
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _make(ctx: Ctx, title: str, *, status: str = "in_progress", days_ago: int = 0,
          patient=None) -> Treatment:
    started = datetime.now(timezone.utc) - timedelta(days=days_ago)
    t = Treatment(
        patient_id=(patient or ctx.patient).id,
        title=title,
        status=status,
        started_at=started,
        closed_at=started if status == "completed" else None,
    )
    ctx.db.add(t)
    ctx.db.commit()
    return t


def test_lists_only_this_patients_treatments(ctx):
    _make(ctx, "Mine")
    _make(ctx, "Someone else's", patient=ctx.other_patient)

    resp = ctx.client.get(f"/treatments?patient_id={ctx.patient.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Mine"
    assert data["items"][0]["patient_id"] == str(ctx.patient.id)


def test_status_filter(ctx):
    _make(ctx, "Open one")
    _make(ctx, "Closed one", status="completed")

    all_of_them = ctx.client.get(f"/treatments?patient_id={ctx.patient.id}").json()
    assert all_of_them["total"] == 2

    open_only = ctx.client.get(
        f"/treatments?patient_id={ctx.patient.id}&status=in_progress"
    ).json()
    assert open_only["total"] == 1
    assert open_only["items"][0]["title"] == "Open one"
    assert open_only["items"][0]["closed_at"] is None

    closed = ctx.client.get(
        f"/treatments?patient_id={ctx.patient.id}&status=completed"
    ).json()
    assert closed["total"] == 1
    assert closed["items"][0]["title"] == "Closed one"
    assert closed["items"][0]["closed_at"] is not None


def test_open_treatments_sort_first(ctx):
    """The visit form's picker wants actionable threads at the top.

    The closed one is the most RECENT, so a plain date sort would put it first —
    this asserts the open-first ordering specifically.
    """
    _make(ctx, "Old open", days_ago=10)
    _make(ctx, "Recent closed", status="completed", days_ago=1)

    items = ctx.client.get(f"/treatments?patient_id={ctx.patient.id}").json()["items"]
    assert [i["title"] for i in items] == ["Old open", "Recent closed"]


def test_newest_first_within_a_group(ctx):
    _make(ctx, "Older", days_ago=10)
    _make(ctx, "Newer", days_ago=1)

    items = ctx.client.get(f"/treatments?patient_id={ctx.patient.id}").json()["items"]
    assert [i["title"] for i in items] == ["Newer", "Older"]


def test_patient_id_is_required(ctx):
    assert ctx.client.get("/treatments").status_code == 422


def test_unknown_status_is_422(ctx):
    assert ctx.client.get(
        f"/treatments?patient_id={ctx.patient.id}&status=finished"
    ).status_code == 422


def test_get_one_and_404(ctx):
    t = _make(ctx, "Fetch me", days_ago=2)

    resp = ctx.client.get(f"/treatments/{t.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Fetch me"
    assert body["status"] == "in_progress"
    assert body["started_at"] is not None

    assert ctx.client.get(f"/treatments/{uuid.uuid4()}").status_code == 404


def test_empty_list_for_a_patient_with_no_treatments(ctx):
    resp = ctx.client.get(f"/treatments?patient_id={ctx.other_patient.id}")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_no_create_or_replace_routes(ctx):
    """Treatments are born from POST /visits; the only writes are close/reopen.

    Pins that there's still no create/replace route on the collection — so one
    can't appear unnoticed. (The /close and /reopen sub-paths ARE writes, tested
    below.)
    """
    t = _make(ctx, "Read only")
    assert ctx.client.post("/treatments", json={"title": "x"}).status_code == 405
    assert ctx.client.patch(f"/treatments/{t.id}", json={"title": "x"}).status_code == 405


# --- lifecycle: close / reopen (step 4.5) ------------------------------------

def test_close_an_open_treatment(ctx):
    t = _make(ctx, "RCT tooth 36")
    assert t.status == "in_progress" and t.closed_at is None

    resp = ctx.client.post(f"/treatments/{t.id}/close")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["closed_at"] is not None

    ctx.db.expire_all()
    row = ctx.db.get(Treatment, t.id)
    assert row.status == "completed" and row.closed_at is not None


def test_reopen_a_completed_treatment(ctx):
    t = _make(ctx, "Old RCT", status="completed", days_ago=5)
    assert t.closed_at is not None

    resp = ctx.client.post(f"/treatments/{t.id}/reopen")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["closed_at"] is None

    ctx.db.expire_all()
    row = ctx.db.get(Treatment, t.id)
    assert row.status == "in_progress" and row.closed_at is None


def test_double_close_is_409(ctx):
    t = _make(ctx, "Cleaning", status="completed")
    assert ctx.client.post(f"/treatments/{t.id}/close").status_code == 409


def test_reopen_an_open_treatment_is_409(ctx):
    t = _make(ctx, "Still going")
    assert ctx.client.post(f"/treatments/{t.id}/reopen").status_code == 409


def test_lifecycle_404s(ctx):
    missing = uuid.uuid4()
    assert ctx.client.post(f"/treatments/{missing}/close").status_code == 404
    assert ctx.client.post(f"/treatments/{missing}/reopen").status_code == 404


def test_close_reopen_are_audited(ctx):
    t = _make(ctx, "Audit me")
    ctx.client.post(f"/treatments/{t.id}/close")
    ctx.client.post(f"/treatments/{t.id}/reopen")

    rows = list(
        ctx.db.scalars(
            select(AuditLog)
            .where(AuditLog.entity == "treatment")
            .where(AuditLog.entity_id == t.id)
        )
    )
    actions = {r.action for r in rows}
    assert {"close", "reopen"} <= actions
    close_row = next(r for r in rows if r.action == "close")
    assert close_row.details == {"from": "in_progress", "to": "completed"}


# --- needs-follow-up report (step 4.8) ---------------------------------------

def _appt(ctx, treatment, *, days_from_now: float, status: str = "booked") -> Appointment:
    a = Appointment(
        patient_id=treatment.patient_id,
        treatment_id=treatment.id,
        start_time=datetime.now(timezone.utc) + timedelta(days=days_from_now),
        status=status,
    )
    ctx.db.add(a)
    ctx.db.commit()
    return a


def _needs_follow_up_ids(ctx) -> set:
    resp = ctx.client.get("/treatments/needs-follow-up")
    assert resp.status_code == 200, resp.text
    return {row["id"] for row in resp.json()["items"]}


def test_open_treatment_with_no_appointment_is_flagged(ctx):
    t = _make(ctx, "RCT, unbooked")
    assert str(t.id) in _needs_follow_up_ids(ctx)


def test_future_appointment_clears_the_flag(ctx):
    t = _make(ctx, "RCT, booked back in")
    _appt(ctx, t, days_from_now=7)
    assert str(t.id) not in _needs_follow_up_ids(ctx)


def test_only_a_past_appointment_still_flags(ctx):
    """The case a 'zero appointments' shortcut would miss: the sitting already
    happened, the next one still isn't booked."""
    t = _make(ctx, "RCT, last sitting in the past")
    _appt(ctx, t, days_from_now=-7)
    assert str(t.id) in _needs_follow_up_ids(ctx)


def test_cancelled_future_appointment_still_flags(ctx):
    t = _make(ctx, "RCT, follow-up cancelled")
    _appt(ctx, t, days_from_now=7, status="cancelled")
    assert str(t.id) in _needs_follow_up_ids(ctx)


def test_completed_treatment_is_never_flagged(ctx):
    t = _make(ctx, "Finished, no appt", status="completed")
    assert str(t.id) not in _needs_follow_up_ids(ctx)


def test_flag_carries_patient_name_and_last_visit(ctx):
    t = _make(ctx, "RCT with visits")
    # Two visits; the report should carry the latest date.
    older = Visit(
        patient_id=ctx.patient.id, treatment_id=t.id,
        visit_date=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
    )
    newer = Visit(
        patient_id=ctx.patient.id, treatment_id=t.id,
        visit_date=datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc),
    )
    ctx.db.add_all([older, newer])
    ctx.db.commit()

    row = next(
        r for r in ctx.client.get("/treatments/needs-follow-up").json()["items"]
        if r["id"] == str(t.id)
    )
    assert row["patient_name"] == ctx.patient.name
    assert row["last_visit_date"].startswith("2026-08-09")


def test_flag_last_visit_none_when_no_visits(ctx):
    t = _make(ctx, "Open, never recorded")
    row = next(
        r for r in ctx.client.get("/treatments/needs-follow-up").json()["items"]
        if r["id"] == str(t.id)
    )
    assert row["last_visit_date"] is None


def test_needs_follow_up_not_shadowed_by_id_route(ctx):
    """The literal path resolves to the report, not GET /{treatment_id} (which
    would 422 trying to parse 'needs-follow-up' as a UUID)."""
    assert ctx.client.get("/treatments/needs-follow-up").status_code == 200
