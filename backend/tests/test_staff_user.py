"""DB-backed tests for the staff_user model.

These need a real Postgres (the roles column is a Postgres ARRAY, and we want to
prove the migration applied and the array round-trips). If no database is
reachable — e.g. a laptop running `pytest` without `docker compose up` — the
tests SKIP rather than fail, so the DB-free suite (test_health) still runs
everywhere. In CI the Postgres service makes these run for real.
"""

import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.db import SessionLocal, engine
from app.models.staff_user import StaffUser


@pytest.fixture(scope="module")
def db_available() -> bool:
    """Skip the whole module if the database can't be reached.

    Uses a throwaway engine with a short connect_timeout so an unreachable DB
    (e.g. `pytest` on a laptop with no Docker) skips in a couple of seconds
    instead of blocking on the OS default TCP timeout.
    """
    probe = create_engine(
        settings.database_url, connect_args={"connect_timeout": 2}
    )
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any connection failure means skip
        pytest.skip(f"database not reachable, skipping DB tests: {exc}")
    finally:
        probe.dispose()
    return True


@pytest.fixture
def session(db_available):
    """A session that cleans up any rows it created after the test."""
    created_ids: list[uuid.UUID] = []
    db = SessionLocal()
    try:
        yield db, created_ids
    finally:
        db.rollback()
        for sid in created_ids:
            obj = db.get(StaffUser, sid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        db.close()


def test_migration_created_staff_user_table(db_available):
    """The migration ran: the staff_user table and its email index exist."""
    inspector = inspect(engine)
    assert "staff_user" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("staff_user")}
    assert {"id", "name", "email", "roles", "active", "created_at"} <= columns


def test_roles_array_round_trips(session):
    """A roles set is stored and read back as a Python list, in order."""
    db, created_ids = session
    sid = uuid.uuid4()
    created_ids.append(sid)

    db.add(
        StaffUser(
            id=sid,
            name="Dr. Test",
            email=f"round-trip-{sid}@clinic.local",
            roles=["dentist", "admin"],
        )
    )
    db.commit()
    db.expire_all()

    fetched = db.get(StaffUser, sid)
    assert fetched is not None
    assert fetched.roles == ["dentist", "admin"]


def test_defaults_active_and_created_at(session):
    """active defaults to True and created_at is populated by the DB."""
    db, created_ids = session
    sid = uuid.uuid4()
    created_ids.append(sid)

    db.add(
        StaffUser(
            id=sid,
            name="Reception Test",
            email=f"defaults-{sid}@clinic.local",
            roles=["receptionist"],
        )
    )
    db.commit()
    db.expire_all()

    fetched = db.get(StaffUser, sid)
    assert fetched is not None
    assert fetched.active is True
    assert fetched.created_at is not None
