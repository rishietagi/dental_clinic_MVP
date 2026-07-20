"""Tests for the appointment model.

All DB-backed (no pure-logic property to test, unlike patient's `age`), so the
whole suite skips fast if no Postgres is reachable — same pattern as the other
DB suites. Appointments reference a patient, so each persistence test creates a
throwaway patient and cleans both up.

Two things beyond the usual insert/defaults are worth proving here because this
is the schema's first table with foreign keys:
- The `patient_id` FK is real (a bad id is rejected by the DB), not decorative.
- `treatment_id`'s FK is real too, **as of step 4.2**. It was deliberately absent
  from 3.1 until the `treatment` table existed, and a test here asserted that
  absence. Now that 4.2 has added the constraint, the same test asserts the
  opposite — a random treatment_id is rejected, a real one commits. Inverted
  rather than deleted so the deferral being paid off stays visible in history.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal, engine
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.treatment import Treatment


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
def session(db_available):
    """Yields (db, cleanup) where cleanup is a list of (Model, id) to delete."""
    cleanup: list[tuple[type, uuid.UUID]] = []
    db = SessionLocal()
    try:
        yield db, cleanup
    finally:
        db.rollback()
        # FK order: appointments reference treatments, treatments reference
        # patients, so delete children first.
        order = [Appointment, Treatment, Patient]
        # Commit after each delete so the FK order above is the order Postgres
        # actually sees (a single trailing commit lets SQLAlchemy reorder them).
        for model, oid in sorted(cleanup, key=lambda t: order.index(t[0])):
            obj = db.get(model, oid)
            if obj is not None:
                db.delete(obj)
                db.commit()
        db.close()


def _make_patient(db, cleanup) -> Patient:
    p = Patient(name="Appt Test Patient")
    db.add(p)
    db.commit()
    cleanup.append((Patient, p.id))
    return p


# --- schema shape ------------------------------------------------------------

def test_migration_created_appointment_table(db_available):
    inspector = inspect(engine)
    assert "appointment" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("appointment")}
    assert {
        "id", "patient_id", "treatment_id", "dentist_id", "start_time",
        "duration_min", "status", "reason", "created_at", "updated_at",
    } <= columns


def test_foreign_keys(db_available):
    """patient_id, dentist_id and (since 4.2) treatment_id are all real FKs."""
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("appointment")
    referred = {
        tuple(fk["constrained_columns"]): fk["referred_table"] for fk in fks
    }
    assert referred.get(("patient_id",)) == "patient"
    assert referred.get(("dentist_id",)) == "staff_user"
    # Added in 4.2, once the `treatment` table existed.
    assert referred.get(("treatment_id",)) == "treatment"


# --- persistence -------------------------------------------------------------

def test_insert_and_defaults(session):
    db, cleanup = session
    patient = _make_patient(db, cleanup)

    appt = Appointment(
        patient_id=patient.id,
        start_time=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
    )
    db.add(appt)
    db.commit()
    cleanup.append((Appointment, appt.id))
    db.expire_all()

    fetched = db.get(Appointment, appt.id)
    assert fetched is not None
    assert fetched.id is not None            # server-generated
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.status == "booked"        # server default
    assert fetched.duration_min == 30        # server default
    assert fetched.treatment_id is None
    assert fetched.dentist_id is None
    assert fetched.reason is None


def test_patient_fk_is_enforced(session):
    """A non-existent patient_id is rejected by the DB — the FK is real."""
    db, cleanup = session
    appt = Appointment(
        patient_id=uuid.uuid4(),  # no such patient
        start_time=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
    )
    db.add(appt)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_treatment_id_fk_is_enforced(session):
    """A random treatment_id is now rejected — the FK is real as of 4.2.

    The inverse of the test this replaces, which asserted the FK's *absence*
    while the deferral stood.
    """
    db, cleanup = session
    patient = _make_patient(db, cleanup)

    appt = Appointment(
        patient_id=patient.id,
        treatment_id=uuid.uuid4(),  # no such treatment
        start_time=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
    )
    db.add(appt)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_treatment_id_accepts_a_real_treatment(session):
    """A follow-up carries the treatment it continues; unset stays allowed."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)

    treatment = Treatment(patient_id=patient.id, title="RCT tooth 36")
    db.add(treatment)
    db.commit()
    cleanup.append((Treatment, treatment.id))

    appt = Appointment(
        patient_id=patient.id,
        treatment_id=treatment.id,
        start_time=datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc),
    )
    db.add(appt)
    db.commit()
    cleanup.append((Appointment, appt.id))
    db.expire_all()

    fetched = db.get(Appointment, appt.id)
    assert fetched is not None
    assert fetched.treatment_id == treatment.id
