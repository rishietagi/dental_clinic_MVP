"""Tests for the clinical core models: treatment, visit, procedure_performed.

All DB-backed, so the suite skips fast if no Postgres is reachable — same
pattern as the other DB suites. These three tables form a chain
(treatment -> visit -> procedure_performed) plus links out to patient,
appointment, staff_user and treatment_item, so cleanup must run child-first.

The assertions worth having here, beyond the usual shape/defaults checks, are
the ones that pin the *domain rule* (BUILD_PLAN §3) into the schema:

- One treatment threads MANY visits — the RCT case, asserted directly.
- `visit.treatment_id` is NOT NULL: a visit can never float free of a treatment.
- `visit.appointment_id` IS nullable: walk-ins are normal, not an error.

If a future change breaks one of those, it should break a test loudly rather
than quietly allowing orphan visits that would corrupt the "open treatments
with no next appointment" report (4.8).
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal, engine
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.procedure_performed import ProcedurePerformed
from app.models.treatment import Treatment
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit


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


# Delete order: children before the parents they point at. Visit comes before
# Appointment because visit.appointment_id references appointment (the scheduled
# path), not the other way round — getting this backwards fails teardown with a
# ForeignKeyViolation rather than a test assertion.
_CLEANUP_ORDER = [
    ProcedurePerformed,
    Visit,
    Appointment,
    Treatment,
    TreatmentItem,
    Patient,
]


@pytest.fixture
def session(db_available):
    """Yields (db, cleanup) where cleanup is a list of (Model, id) to delete."""
    cleanup: list[tuple[type, uuid.UUID]] = []
    db = SessionLocal()
    try:
        yield db, cleanup
    finally:
        db.rollback()
        # Commit after each delete: db.delete() only stages the row, and a
        # single commit at the end lets SQLAlchemy choose its own flush order,
        # which ignores _CLEANUP_ORDER and trips the FKs.
        for model, oid in sorted(cleanup, key=lambda t: _CLEANUP_ORDER.index(t[0])):
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _make_patient(db, cleanup) -> Patient:
    p = Patient(name="Treatment Test Patient")
    db.add(p)
    db.commit()
    cleanup.append((Patient, p.id))
    return p


def _make_treatment(db, cleanup, patient, **kwargs) -> Treatment:
    t = Treatment(patient_id=patient.id, title=kwargs.pop("title", "RCT tooth 36"), **kwargs)
    db.add(t)
    db.commit()
    cleanup.append((Treatment, t.id))
    return t


# --- schema shape ------------------------------------------------------------

def test_migration_created_tables(db_available):
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    assert {"treatment", "visit", "procedure_performed"} <= names

    treatment_cols = {c["name"] for c in inspector.get_columns("treatment")}
    assert {
        "id", "patient_id", "title", "tooth_ref", "status",
        "started_at", "closed_at", "created_at", "updated_at",
    } <= treatment_cols

    visit_cols = {c["name"] for c in inspector.get_columns("visit")}
    assert {
        "id", "patient_id", "treatment_id", "appointment_id", "dentist_id",
        "visit_date", "complaint", "clinical_notes", "created_at", "updated_at",
    } <= visit_cols

    proc_cols = {c["name"] for c in inspector.get_columns("procedure_performed")}
    assert {"id", "visit_id", "treatment_item_id", "tooth_ref"} <= proc_cols


def test_foreign_keys(db_available):
    inspector = inspect(engine)

    def referred(table: str) -> dict[tuple[str, ...], str]:
        return {
            tuple(fk["constrained_columns"]): fk["referred_table"]
            for fk in inspector.get_foreign_keys(table)
        }

    assert referred("treatment").get(("patient_id",)) == "patient"

    visit_fks = referred("visit")
    assert visit_fks.get(("patient_id",)) == "patient"
    assert visit_fks.get(("treatment_id",)) == "treatment"
    assert visit_fks.get(("appointment_id",)) == "appointment"
    assert visit_fks.get(("dentist_id",)) == "staff_user"

    proc_fks = referred("procedure_performed")
    assert proc_fks.get(("visit_id",)) == "visit"
    assert proc_fks.get(("treatment_item_id",)) == "treatment_item"


def test_visit_nullability(db_available):
    """treatment_id is required; appointment_id and dentist_id are not."""
    inspector = inspect(engine)
    nullable = {c["name"]: c["nullable"] for c in inspector.get_columns("visit")}
    assert nullable["treatment_id"] is False   # the thread is mandatory
    assert nullable["patient_id"] is False
    assert nullable["appointment_id"] is True  # walk-ins
    assert nullable["dentist_id"] is True


# --- persistence -------------------------------------------------------------

def test_treatment_insert_and_defaults(session):
    db, cleanup = session
    patient = _make_patient(db, cleanup)
    treatment = _make_treatment(db, cleanup, patient)
    db.expire_all()

    fetched = db.get(Treatment, treatment.id)
    assert fetched is not None
    assert fetched.id is not None                  # server-generated
    assert fetched.status == "in_progress"         # server default
    assert fetched.started_at is not None          # server default
    assert fetched.closed_at is None               # open until closed (4.5)
    assert fetched.tooth_ref is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_treatment_threads_multiple_visits(session):
    """The domain rule: one treatment, many sittings (the RCT case)."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)
    treatment = _make_treatment(db, cleanup, patient, tooth_ref="36")

    start = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)
    notes = ["access opening, temp filling", "cleaning & shaping", "obturation + crown"]
    for i, note in enumerate(notes):
        v = Visit(
            patient_id=patient.id,
            treatment_id=treatment.id,
            visit_date=start + timedelta(days=7 * i),
            clinical_notes=note,
        )
        db.add(v)
        db.commit()
        cleanup.append((Visit, v.id))

    db.expire_all()
    visits = (
        db.query(Visit)
        .filter(Visit.treatment_id == treatment.id)
        .order_by(Visit.visit_date)
        .all()
    )
    assert len(visits) == 3
    assert [v.clinical_notes for v in visits] == notes
    # All three hang off the one treatment — that's the thread.
    assert {v.treatment_id for v in visits} == {treatment.id}


def test_visit_requires_a_treatment(session):
    """A visit with no treatment is rejected — no orphan visits."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)

    db.add(Visit(patient_id=patient.id, treatment_id=None))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_visit_treatment_fk_is_enforced(session):
    """A treatment_id pointing at nothing is rejected by the DB."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)

    db.add(Visit(patient_id=patient.id, treatment_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_walk_in_visit_has_no_appointment(session):
    """appointment_id is nullable: a walk-in is normal, not an error."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)
    treatment = _make_treatment(db, cleanup, patient, title="Scaling")

    v = Visit(patient_id=patient.id, treatment_id=treatment.id, complaint="Bleeding gums")
    db.add(v)
    db.commit()  # would raise if appointment_id were required
    cleanup.append((Visit, v.id))
    db.expire_all()

    fetched = db.get(Visit, v.id)
    assert fetched is not None
    assert fetched.appointment_id is None
    assert fetched.dentist_id is None
    assert fetched.visit_date is not None  # server default
    assert fetched.clinical_notes is None


def test_procedure_performed_links_visit_to_catalogue(session):
    """A visit can contain several procedures, each priced by a catalogue item."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)
    treatment = _make_treatment(db, cleanup, patient)

    item = TreatmentItem(
        name=f"Test Procedure {uuid.uuid4().hex[:8]}",  # name is unique
        default_price=Decimal("1200.50"),
    )
    db.add(item)
    db.commit()
    cleanup.append((TreatmentItem, item.id))

    v = Visit(patient_id=patient.id, treatment_id=treatment.id)
    db.add(v)
    db.commit()
    cleanup.append((Visit, v.id))

    for tooth in ("36", None):
        p = ProcedurePerformed(
            visit_id=v.id, treatment_item_id=item.id, tooth_ref=tooth
        )
        db.add(p)
        db.commit()
        cleanup.append((ProcedurePerformed, p.id))

    db.expire_all()
    procs = db.query(ProcedurePerformed).filter(ProcedurePerformed.visit_id == v.id).all()
    assert len(procs) == 2
    assert {p.tooth_ref for p in procs} == {"36", None}
    assert {p.treatment_item_id for p in procs} == {item.id}


def test_procedure_treatment_item_fk_is_enforced(session):
    """A procedure must reference a real catalogue item."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)
    treatment = _make_treatment(db, cleanup, patient)

    v = Visit(patient_id=patient.id, treatment_id=treatment.id)
    db.add(v)
    db.commit()
    cleanup.append((Visit, v.id))

    db.add(ProcedurePerformed(visit_id=v.id, treatment_item_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_visit_can_link_to_an_appointment(session):
    """The scheduled path: appointment -> visit, both on the same treatment."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)
    treatment = _make_treatment(db, cleanup, patient)

    appt = Appointment(
        patient_id=patient.id,
        treatment_id=treatment.id,  # a follow-up carries its treatment (4.6)
        start_time=datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc),
    )
    db.add(appt)
    db.commit()
    cleanup.append((Appointment, appt.id))

    v = Visit(
        patient_id=patient.id,
        treatment_id=treatment.id,
        appointment_id=appt.id,
    )
    db.add(v)
    db.commit()
    cleanup.append((Visit, v.id))
    db.expire_all()

    fetched = db.get(Visit, v.id)
    assert fetched is not None
    assert fetched.appointment_id == appt.id
    assert fetched.treatment_id == treatment.id
