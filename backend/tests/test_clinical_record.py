"""The OPD clinical record — examination, diagnosis, investigations (step 6.10).

These pin the fields the clinic's paper out-patient card actually carries, which
the app had nowhere to store before 6.10 — most glaringly the **diagnosis**, the
clinical conclusion of the whole visit.

Also covered: the `V-1042` visit number, the treatment `phase`, and the recall
list that drives Phase 4 (maintenance) of the treatment workflow.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

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
    def __init__(self, db, staff, patient, item):
        self.db = db
        self.staff = staff
        self.patient = patient
        self.item = item
        self.client = client
        self.extra_patients: list[uuid.UUID] = []


@pytest.fixture
def ctx(db_available):
    db = SessionLocal()
    staff = StaffUser(
        id=uuid.uuid4(),
        name="Clinical Dentist",
        email=f"{uuid.uuid4()}@clinic.local",
        roles=["dentist", "admin"],
        active=True,
    )
    patient = Patient(name="Clinical Test Patient")
    item = TreatmentItem(
        name=f"Clinical Item {uuid.uuid4().hex[:8]}", default_price="600.00"
    )
    db.add_all([staff, patient, item])
    db.commit()
    app.dependency_overrides[get_current_claims] = lambda: {"sub": str(staff.id)}

    c = Ctx(db, staff, patient, item)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        db.rollback()
        pids = [patient.id, *c.extra_patients]

        for vid in [v.id for v in db.scalars(select(Visit).where(Visit.patient_id.in_(pids)))]:
            for proc in db.scalars(
                select(ProcedurePerformed).where(ProcedurePerformed.visit_id == vid)
            ):
                db.delete(proc)
            db.commit()
            db.delete(db.get(Visit, vid))
            db.commit()
        for t in db.scalars(select(Treatment).where(Treatment.patient_id.in_(pids))):
            db.delete(t)
            db.commit()
        for row in db.scalars(select(AuditLog).where(AuditLog.actor_id == staff.id)):
            db.delete(row)
        db.commit()
        for pid in pids:
            obj = db.get(Patient, pid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        for model, oid in [(TreatmentItem, item.id), (StaffUser, staff.id)]:
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


# The sample OPD card the clinic sent, transcribed.
CARD = {
    "complaint": "Pain in upper left back tooth region since 3 days",
    "history_note": "NRMH",
    "bp_systolic": 118,
    "bp_diastolic": 76,
    "habits": "Nil",
    "extra_oral": "NAD",
    "intra_oral": "NAD",
    "soft_tissues": "NAD",
    "hard_tissue": "Proximal caries 26",
    "occlusion": "Mesial step terminal plane",
    "missing_teeth": "Nil",
    "other_findings": "-",
    "investigations": ["iopa"],
    "investigation_notes": "IOPA wrt 26",
    "provisional_diagnosis": "Chronic irreversible pulpitis 26",
    "differential_diagnosis": "Reversible pulpitis",
    "final_diagnosis": "Chronic irreversible pulpitis 26",
    "referred_to": "Cons. & Endo",
    "referral_note": "For RCT",
}


def _record(ctx: Ctx, **overrides) -> dict:
    body = {
        "patient_id": str(ctx.patient.id),
        "treatment": {"title": "RCT tooth 26", "tooth_ref": "26"},
        "procedures": [{"treatment_item_id": str(ctx.item.id), "tooth_ref": "26"}],
        "treatment_status": "in_progress",
        **CARD,
        **overrides,
    }
    resp = ctx.client.post("/visits", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- the card round-trips ----------------------------------------------------

def test_whole_opd_card_round_trips(ctx):
    """Every field on the paper card is stored and returned unchanged."""
    created = _record(ctx)
    fetched = ctx.client.get(f"/visits/{created['id']}").json()

    for field, expected in CARD.items():
        assert created[field] == expected, f"{field} wrong on create"
        assert fetched[field] == expected, f"{field} wrong on read"


def test_diagnosis_is_recorded(ctx):
    """The headline gap 6.10 closes — before this, a diagnosis had nowhere to go."""
    v = _record(ctx)
    assert v["provisional_diagnosis"] == "Chronic irreversible pulpitis 26"
    assert v["final_diagnosis"] == "Chronic irreversible pulpitis 26"
    assert v["differential_diagnosis"] == "Reversible pulpitis"


def test_clinical_fields_are_all_optional(ctx):
    """A routine scaling fills almost none of the card. It must still record."""
    resp = ctx.client.post(
        "/visits",
        json={
            "patient_id": str(ctx.patient.id),
            "treatment": {"title": "Scaling", "tooth_ref": None},
            "procedures": [],
            "treatment_status": "completed",
        },
    )
    assert resp.status_code == 201, resp.text
    v = resp.json()
    assert v["provisional_diagnosis"] is None
    assert v["habits"] is None
    assert v["investigations"] == []  # a list, never null


def test_diagnosis_can_be_revised_by_patch(ctx):
    """Provisional -> final is the normal path once an X-ray comes back."""
    v = _record(ctx, final_diagnosis=None)
    assert v["final_diagnosis"] is None

    resp = ctx.client.patch(
        f"/visits/{v['id']}", json={"final_diagnosis": "Necrotic pulp 26"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["final_diagnosis"] == "Necrotic pulp 26"
    # An unrelated field must survive the PATCH untouched.
    assert resp.json()["provisional_diagnosis"] == CARD["provisional_diagnosis"]


def test_patch_without_investigations_does_not_wipe_them(ctx):
    """`investigations` defaults to [] on create; a PATCH that omits it must
    leave the stored list alone rather than clearing it."""
    v = _record(ctx)
    assert v["investigations"] == ["iopa"]

    resp = ctx.client.patch(f"/visits/{v['id']}", json={"habits": "Tobacco chewing"})
    assert resp.status_code == 200
    assert resp.json()["investigations"] == ["iopa"]
    assert resp.json()["habits"] == "Tobacco chewing"


# --- investigations ----------------------------------------------------------

def test_investigations_accepts_the_known_set(ctx):
    v = _record(ctx, investigations=["iopa", "opg_digital"])
    assert v["investigations"] == ["iopa", "opg_digital"]


def test_unknown_investigation_rejected(ctx):
    """A Literal, so junk is a 422 long before it reaches the column."""
    resp = ctx.client.post(
        "/visits",
        json={
            "patient_id": str(ctx.patient.id),
            "treatment": {"title": "X", "tooth_ref": None},
            "procedures": [],
            "treatment_status": "completed",
            "investigations": ["mri"],
        },
    )
    assert resp.status_code == 422


# --- vitals ------------------------------------------------------------------

def test_bp_is_recorded(ctx):
    v = _record(ctx)
    assert (v["bp_systolic"], v["bp_diastolic"]) == (118, 76)


@pytest.mark.parametrize(
    "systolic,diastolic",
    [(10, 76), (400, 76), (118, 5), (118, 500)],
)
def test_implausible_bp_rejected(ctx, systolic, diastolic):
    """A typo guard, not a clinical judgement — the bounds are deliberately wide."""
    resp = ctx.client.post(
        "/visits",
        json={
            "patient_id": str(ctx.patient.id),
            "treatment": {"title": "X", "tooth_ref": None},
            "procedures": [],
            "treatment_status": "completed",
            "bp_systolic": systolic,
            "bp_diastolic": diastolic,
        },
    )
    assert resp.status_code == 422


# --- the V- number -----------------------------------------------------------

def test_visit_gets_a_readable_number(ctx):
    """Shown as V-1042. A UUID can't be quoted down a phone or written on paper."""
    v = _record(ctx)
    assert isinstance(v["number"], int)
    assert v["number"] >= 1001


def test_visit_numbers_are_unique_and_increasing(ctx):
    a = _record(ctx)
    b = _record(ctx)
    assert b["number"] > a["number"]


# --- treatment phase ---------------------------------------------------------

def test_set_and_clear_treatment_phase(ctx):
    v = _record(ctx)
    tid = v["treatment_id"]

    resp = ctx.client.post(f"/treatments/{tid}/phase", json={"phase": 2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["phase"] == 2

    # Phases move forward, back, or skip — real plans do, so none of it 409s.
    assert ctx.client.post(f"/treatments/{tid}/phase", json={"phase": 4}).json()["phase"] == 4
    assert ctx.client.post(f"/treatments/{tid}/phase", json={"phase": 1}).json()["phase"] == 1

    cleared = ctx.client.post(f"/treatments/{tid}/phase", json={"phase": None})
    assert cleared.status_code == 200
    assert cleared.json()["phase"] is None


@pytest.mark.parametrize("bad", [0, 5, -1, 99])
def test_invalid_phase_rejected(ctx, bad):
    v = _record(ctx)
    resp = ctx.client.post(f"/treatments/{v['treatment_id']}/phase", json={"phase": bad})
    assert resp.status_code == 422


def test_phase_shows_on_the_treatment_and_its_visits(ctx):
    v = _record(ctx)
    tid = v["treatment_id"]
    ctx.client.post(f"/treatments/{tid}/phase", json={"phase": 3})

    assert ctx.client.get(f"/treatments/{tid}").json()["phase"] == 3
    # And on the treatment summary nested in a visit read.
    assert ctx.client.get(f"/visits/{v['id']}").json()["treatment"]["phase"] == 3


def test_phase_endpoint_does_not_add_a_general_patch(ctx):
    """The treatments router still exposes no replace route (the 4.5 rule)."""
    v = _record(ctx)
    assert ctx.client.patch(f"/treatments/{v['treatment_id']}", json={"title": "x"}).status_code == 405


# --- patient guardian / address ---------------------------------------------

def test_guardian_and_address_round_trip(ctx):
    """The card's "S/O" line — paediatric patients need a guardian recorded."""
    resp = ctx.client.post(
        "/patients",
        json={
            "name": "Taimur Test",
            "phone": "8197401665",
            "guardian_name": "S/O Sharuk Khan",
            "address": "Davangere",
        },
    )
    assert resp.status_code == 201, resp.text
    pid = uuid.UUID(resp.json()["id"])
    ctx.extra_patients.append(pid)

    fetched = ctx.client.get(f"/patients/{pid}").json()
    assert fetched["guardian_name"] == "S/O Sharuk Khan"
    assert fetched["address"] == "Davangere"


# --- recalls (Phase 4) -------------------------------------------------------

def _make_patient(ctx, name, recall_due) -> str:
    resp = ctx.client.post(
        "/patients", json={"name": name, "recall_due": recall_due}
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    ctx.extra_patients.append(uuid.UUID(pid))
    return pid


def test_recalls_due_lists_only_the_due(ctx):
    today = date.today()
    overdue = _make_patient(ctx, "Recall Overdue", str(today - timedelta(days=30)))
    due_today = _make_patient(ctx, "Recall Today", str(today))
    future = _make_patient(ctx, "Recall Later", str(today + timedelta(days=60)))

    resp = ctx.client.get("/patients/recalls-due")
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()["items"]}

    assert overdue in ids
    assert due_today in ids
    assert future not in ids, "a recall two months out is not due yet"


def test_recalls_due_within_days_widens_the_window(ctx):
    soon = _make_patient(ctx, "Recall Soon", str(date.today() + timedelta(days=10)))

    assert soon not in {r["id"] for r in ctx.client.get("/patients/recalls-due").json()["items"]}
    widened = ctx.client.get("/patients/recalls-due", params={"within_days": 14}).json()
    assert soon in {r["id"] for r in widened["items"]}


def test_recalls_exclude_archived_patients(ctx):
    """Chasing someone who has left the practice is noise."""
    pid = _make_patient(ctx, "Recall Gone", str(date.today() - timedelta(days=5)))
    ctx.client.post(f"/patients/{pid}/archive")

    ids = {r["id"] for r in ctx.client.get("/patients/recalls-due").json()["items"]}
    assert pid not in ids


def test_recalls_due_carries_no_medical_notes(ctx):
    """Bulk lists never carry sensitive notes — the PatientListItem rule."""
    _make_patient(ctx, "Recall Priv", str(date.today()))
    rows = ctx.client.get("/patients/recalls-due").json()["items"]
    assert rows
    assert set(rows[0].keys()) == {"id", "name", "phone", "recall_due"}


def test_recalls_due_not_shadowed_by_id_route(ctx):
    """`/patients/recalls-due` must be declared before `/patients/{patient_id}`
    or the literal parses as a UUID and 422s (the standing trap)."""
    assert ctx.client.get("/patients/recalls-due").status_code == 200
