"""Tests for the patient seed.

generate_patients() is pure (no DB) so most assertions run everywhere. A light
DB test confirms the generated objects actually persist; it cleans up after
itself and skips if no database is reachable.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from app.db import SessionLocal
from app.models.patient import Patient
from app.seed_patients import SEED_COUNT, generate_patients


# --- generator: pure, no DB --------------------------------------------------

def test_generates_requested_count():
    assert len(generate_patients(count=SEED_COUNT)) == SEED_COUNT
    assert len(generate_patients(count=5)) == 5


def test_generated_fields_look_reasonable():
    patients = generate_patients(count=SEED_COUNT)

    for p in patients:
        assert p.name and " " in p.name                 # "First Last"
        assert p.phone and p.phone.startswith("+91") and len(p.phone) == 13
        assert p.gender in {"Male", "Female"}
        assert isinstance(p.date_of_birth, date)
        assert p.age is not None and 0 <= p.age <= 100   # computed property is sane

    # Some — but not all — have medical notes (so the banner shows in the seed set).
    with_notes = [p for p in patients if p.medical_notes]
    assert 0 < len(with_notes) < SEED_COUNT

    # A few are archived (so the archived filter has something to hide).
    assert any(p.archived for p in patients)


def test_generation_is_deterministic():
    a = generate_patients(count=10, seed=123)
    b = generate_patients(count=10, seed=123)
    assert [p.name for p in a] == [p.name for p in b]


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


def test_generated_patients_persist(db_available):
    """Insert a few generated patients, confirm they save, then clean up."""
    db = SessionLocal()
    created: list[uuid.UUID] = []
    try:
        sample = generate_patients(count=3, seed=999)
        db.add_all(sample)
        db.commit()
        for p in sample:
            created.append(p.id)
            assert p.id is not None
            assert p.created_at is not None

        fetched = db.get(Patient, created[0])
        assert fetched is not None
        assert fetched.age is not None
    finally:
        for pid in created:
            obj = db.get(Patient, pid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        db.close()
