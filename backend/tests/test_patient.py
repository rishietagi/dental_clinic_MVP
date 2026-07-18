"""Tests for the patient model.

The `age` property is pure logic and tested without a database (runs everywhere).
The persistence tests are DB-backed and skip fast if no Postgres is reachable,
like the other DB suites.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.db import SessionLocal, engine
from app.models.patient import Patient


# --- age property: pure logic, no DB -----------------------------------------

def test_age_none_when_dob_unknown():
    assert Patient(name="X", date_of_birth=None).age is None


def test_age_computed_from_dob():
    today = date.today()
    # Someone born exactly 30 years ago today is 30.
    dob = date(today.year - 30, today.month, today.day)
    assert Patient(name="X", date_of_birth=dob).age == 30


def test_age_not_yet_had_birthday_this_year():
    today = date.today()
    # Born 30 years ago but the birthday is one day away -> still 29.
    from datetime import timedelta

    future = today + timedelta(days=1)
    # guard against Feb 29 edge — pick a birthday that reliably exists next year
    try:
        dob = date(today.year - 30, future.month, future.day)
    except ValueError:
        pytest.skip("date edge (leap day); logic is covered by the other cases")
    assert Patient(name="X", date_of_birth=dob).age == 29


# --- persistence: DB-backed --------------------------------------------------

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
    created: list[uuid.UUID] = []
    db = SessionLocal()
    try:
        yield db, created
    finally:
        db.rollback()
        for pid in created:
            obj = db.get(Patient, pid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        db.close()


def test_migration_created_patient_table(db_available):
    inspector = inspect(engine)
    assert "patient" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("patient")}
    assert {
        "id", "name", "phone", "date_of_birth", "gender",
        "medical_notes", "archived", "created_at", "updated_at",
    } <= columns


def test_insert_and_defaults(session):
    db, created = session
    p = Patient(name="Asha Rao", phone="+919812345678", date_of_birth=date(1990, 5, 1))
    db.add(p)
    db.commit()
    created.append(p.id)
    db.expire_all()

    fetched = db.get(Patient, p.id)
    assert fetched is not None
    assert fetched.id is not None           # server-generated
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.archived is False        # default
    assert fetched.age == date.today().year - 1990 - (
        (date.today().month, date.today().day) < (5, 1)
    )


def test_nullable_fields_accept_none(session):
    db, created = session
    p = Patient(name="Walk-in", phone=None, date_of_birth=None, gender=None, medical_notes=None)
    db.add(p)
    db.commit()
    created.append(p.id)
    db.expire_all()

    fetched = db.get(Patient, p.id)
    assert fetched is not None
    assert fetched.phone is None
    assert fetched.date_of_birth is None
    assert fetched.age is None
