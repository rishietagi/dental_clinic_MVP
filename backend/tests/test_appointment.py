"""Tests for the appointment model.

All DB-backed (no pure-logic property to test, unlike patient's `age`), so the
whole suite skips fast if no Postgres is reachable — same pattern as the other
DB suites. Appointments reference a patient, so each persistence test creates a
throwaway patient and cleans both up.

Two things beyond the usual insert/defaults are worth proving here because this
is the schema's first table with foreign keys:
- The `patient_id` FK is real (a bad id is rejected by the DB), not decorative.
- `treatment_id` has NO FK yet (a random id inserts fine) — the Phase 4 deferral,
  asserted behaviourally so a future FK addition is a deliberate, visible change.
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
        # Delete appointments before patients (FK order).
        for model, oid in sorted(cleanup, key=lambda t: t[0] is Patient):
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
    """patient_id and dentist_id are FKs; treatment_id is NOT (deferred to Phase 4)."""
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys("appointment")
    referred = {
        tuple(fk["constrained_columns"]): fk["referred_table"] for fk in fks
    }
    assert referred.get(("patient_id",)) == "patient"
    assert referred.get(("dentist_id",)) == "staff_user"
    # The deferral: treatment_id has no FK until Phase 4.
    constrained = {tuple(fk["constrained_columns"]) for fk in fks}
    assert ("treatment_id",) not in constrained


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


def test_treatment_id_has_no_fk_yet(session):
    """A random treatment_id inserts fine — no FK constraint until Phase 4."""
    db, cleanup = session
    patient = _make_patient(db, cleanup)

    appt = Appointment(
        patient_id=patient.id,
        treatment_id=uuid.uuid4(),  # no treatment table exists; must NOT be rejected
        start_time=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
    )
    db.add(appt)
    db.commit()  # would raise IntegrityError if a FK existed
    cleanup.append((Appointment, appt.id))
    db.expire_all()

    fetched = db.get(Appointment, appt.id)
    assert fetched is not None
    assert fetched.treatment_id is not None
