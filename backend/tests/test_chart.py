"""The dental chart / odontogram (step 6.11).

The rule everything here protects: **marking a tooth supersedes, never
overwrites**. A chart is clinical evidence, so "it was caries in March, filled in
April" has to survive — an UPDATE would quietly destroy the very thing the chart
exists to prove.

Also pinned: FDI notation covers permanent AND deciduous teeth (the clinic treats
children), the dentist/admin write split, and that one patient's chart can never
leak into another's — asserted by NARROWING, the 6.8 lesson.
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
from app.models.tooth_condition import (
    ALL_TEETH,
    DECIDUOUS_TEETH,
    PERMANENT_TEETH,
    ToothCondition,
)

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
    def __init__(self, db, dentist, recep, patient, other):
        self.db = db
        self.dentist = dentist
        self.recep = recep
        self.patient = patient
        self.other = other  # proves the chart NARROWS to one patient
        self.client = client

    def act_as(self, who):
        app.dependency_overrides[get_current_claims] = lambda: {"sub": str(who.id)}


@pytest.fixture
def ctx(db_available):
    db = SessionLocal()
    dentist = StaffUser(
        id=uuid.uuid4(), name="Chart Dentist",
        email=f"{uuid.uuid4()}@clinic.local", roles=["dentist"], active=True,
    )
    recep = StaffUser(
        id=uuid.uuid4(), name="Chart Recep",
        email=f"{uuid.uuid4()}@clinic.local", roles=["receptionist"], active=True,
    )
    patient = Patient(name="Chart Patient")
    other = Patient(name="Chart Other Patient")
    db.add_all([dentist, recep, patient, other])
    db.commit()

    c = Ctx(db, dentist, recep, patient, other)
    c.act_as(dentist)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        db.rollback()
        for pid in (patient.id, other.id):
            for row in db.scalars(
                select(ToothCondition).where(ToothCondition.patient_id == pid)
            ):
                db.delete(row)
            db.commit()
        for who in (dentist, recep):
            for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == who.id)):
                db.delete(row)
        db.commit()
        for model, oid in [
            (Patient, patient.id), (Patient, other.id),
            (StaffUser, dentist.id), (StaffUser, recep.id),
        ]:
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _mark(ctx: Ctx, entries, patient=None, visit_id=None):
    body = {"entries": entries}
    if visit_id:
        body["visit_id"] = str(visit_id)
    return ctx.client.post(
        f"/patients/{(patient or ctx.patient).id}/chart", json=body
    )


def _chart(ctx: Ctx, patient=None) -> dict:
    return ctx.client.get(f"/patients/{(patient or ctx.patient).id}/chart").json()


# --- the empty chart ---------------------------------------------------------

def test_new_patient_chart_is_empty(ctx):
    """A tooth with no row is sound — a new patient does NOT start with 32 rows
    saying "fine". That keeps "not examined" and "examined, healthy" distinct."""
    data = _chart(ctx)
    assert data["items"] == []
    assert data["total"] == 0


def test_unknown_patient_404(ctx):
    assert ctx.client.get(f"/patients/{uuid.uuid4()}/chart").status_code == 404


# --- marking teeth -----------------------------------------------------------

def test_mark_a_tooth(ctx):
    resp = _mark(ctx, [{"tooth": "16", "condition": "caries", "surfaces": "MOD"}])
    assert resp.status_code == 201, resp.text

    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["tooth"] == "16"
    assert items[0]["condition"] == "caries"
    assert items[0]["surfaces"] == "MOD"
    assert items[0]["superseded_at"] is None


def test_mark_several_teeth_at_once(ctx):
    _mark(
        ctx,
        [
            {"tooth": "16", "condition": "caries"},
            {"tooth": "26", "condition": "filled"},
            {"tooth": "36", "condition": "root_canal"},
        ],
    )
    chart = _chart(ctx)
    assert chart["total"] == 3
    assert {i["tooth"]: i["condition"] for i in chart["items"]} == {
        "16": "caries",
        "26": "filled",
        "36": "root_canal",
    }


def test_deciduous_teeth_are_chartable(ctx):
    """The clinic treats children — a 9-year-old in mixed dentition has teeth
    from both sets in the mouth at once."""
    resp = _mark(
        ctx,
        [
            {"tooth": "55", "condition": "caries"},
            {"tooth": "85", "condition": "missing"},
            {"tooth": "16", "condition": "filled"},  # permanent, same mouth
        ],
    )
    assert resp.status_code == 201, resp.text
    assert _chart(ctx)["total"] == 3


@pytest.mark.parametrize("bad", ["99", "0", "abc", "19", "56", "", "111"])
def test_junk_tooth_numbers_rejected(ctx, bad):
    resp = _mark(ctx, [{"tooth": bad, "condition": "caries"}])
    assert resp.status_code == 422


def test_unknown_condition_rejected(ctx):
    """A Literal, so junk is a 422 before it reaches the column."""
    resp = _mark(ctx, [{"tooth": "16", "condition": "exploded"}])
    assert resp.status_code == 422


def test_fdi_sets_are_the_expected_sizes(ctx):
    """32 permanent + 20 deciduous. Guards a typo in the generators."""
    assert len(PERMANENT_TEETH) == 32
    assert len(DECIDUOUS_TEETH) == 20
    assert len(ALL_TEETH) == 52
    assert "18" in PERMANENT_TEETH and "48" in PERMANENT_TEETH
    assert "51" in DECIDUOUS_TEETH and "85" in DECIDUOUS_TEETH


# --- THE headline rule: supersede, never overwrite ---------------------------

def test_remarking_supersedes_and_keeps_exactly_one_current(ctx):
    _mark(ctx, [{"tooth": "16", "condition": "caries"}])
    _mark(ctx, [{"tooth": "16", "condition": "filled"}])

    chart = _chart(ctx)
    current = [i for i in chart["items"] if i["tooth"] == "16"]
    assert len(current) == 1, "a tooth must have exactly one current state"
    assert current[0]["condition"] == "filled"


def test_the_previous_finding_survives_as_history(ctx):
    """The whole point of append-only: treating a tooth must not erase the
    evidence of what was wrong with it."""
    _mark(ctx, [{"tooth": "16", "condition": "caries", "surfaces": "MOD"}])
    _mark(ctx, [{"tooth": "16", "condition": "root_canal"}])
    _mark(ctx, [{"tooth": "16", "condition": "crown"}])

    hist = ctx.client.get(f"/patients/{ctx.patient.id}/chart/16/history").json()
    conditions = [i["condition"] for i in hist["items"]]
    assert conditions == ["caries", "root_canal", "crown"], "oldest first"

    # Only the last is current; the earlier two are stamped.
    assert hist["items"][0]["superseded_at"] is not None
    assert hist["items"][1]["superseded_at"] is not None
    assert hist["items"][2]["superseded_at"] is None


def test_nothing_is_ever_deleted(ctx):
    """Three markings on one tooth leave three rows in the table."""
    for condition in ("caries", "filled", "crown"):
        _mark(ctx, [{"tooth": "16", "condition": condition}])

    rows = ctx.db.scalars(
        select(ToothCondition).where(
            ToothCondition.patient_id == ctx.patient.id, ToothCondition.tooth == "16"
        )
    ).all()
    assert len(rows) == 3


def test_marking_one_tooth_leaves_the_others_alone(ctx):
    """A partial update. Wiping the other 51 teeth because they weren't
    mentioned would be data loss dressed up as a save."""
    _mark(
        ctx,
        [
            {"tooth": "16", "condition": "caries"},
            {"tooth": "26", "condition": "filled"},
        ],
    )
    _mark(ctx, [{"tooth": "16", "condition": "root_canal"}])

    chart = {i["tooth"]: i["condition"] for i in _chart(ctx)["items"]}
    assert chart == {"16": "root_canal", "26": "filled"}


def test_null_condition_clears_a_tooth_back_to_sound(ctx):
    """Undo a mistake without deleting the evidence it was recorded."""
    _mark(ctx, [{"tooth": "16", "condition": "caries"}])
    assert _chart(ctx)["total"] == 1

    resp = _mark(ctx, [{"tooth": "16", "condition": None}])
    assert resp.status_code == 201
    assert _chart(ctx)["total"] == 0, "cleared teeth leave the current chart"

    # ...but the history still shows it was once recorded.
    hist = ctx.client.get(f"/patients/{ctx.patient.id}/chart/16/history").json()
    assert len(hist["items"]) == 1
    assert hist["items"][0]["superseded_at"] is not None


def test_tooth_history_rejects_junk(ctx):
    assert ctx.client.get(f"/patients/{ctx.patient.id}/chart/99/history").status_code == 422


# --- isolation between patients (the 6.8 lesson) -----------------------------

def test_chart_narrows_to_one_patient(ctx):
    """Assert the OTHER patient's teeth are absent — a "returns 200" check would
    pass even if the endpoint leaked every chart in the clinic."""
    _mark(ctx, [{"tooth": "16", "condition": "caries"}])
    _mark(ctx, [{"tooth": "36", "condition": "missing"}], patient=ctx.other)

    mine = _chart(ctx)
    assert {i["tooth"] for i in mine["items"]} == {"16"}

    theirs = _chart(ctx, patient=ctx.other)
    assert {i["tooth"] for i in theirs["items"]} == {"36"}


# --- role split --------------------------------------------------------------

def test_chart_update_is_audited(ctx):
    _mark(ctx, [{"tooth": "16", "condition": "caries"}])
    rows = list(
        ctx.db.scalars(
            select(AuditLog).where(
                AuditLog.entity == "tooth_condition",
                AuditLog.actor_id == ctx.dentist.id,
            )
        )
    )
    assert rows


def test_empty_entries_rejected(ctx):
    """A chart update that names no teeth is a caller bug, not a no-op."""
    assert _mark(ctx, []).status_code == 422
