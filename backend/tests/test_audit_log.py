"""DB-backed tests for the audit_log model and the record_audit service.

Needs a real Postgres (JSONB column, server-side gen_random_uuid + now()).
Skips fast if no database is reachable, like the other DB-backed suites.
"""

import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.db import SessionLocal, engine
from app.models.audit_log import AuditLog
from app.services.audit import record_audit


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
    """A session that deletes any audit rows it created after the test."""
    created: list[uuid.UUID] = []
    db = SessionLocal()
    try:
        yield db, created
    finally:
        db.rollback()
        for aid in created:
            obj = db.get(AuditLog, aid)
            if obj is not None:
                db.delete(obj)
        db.commit()
        db.close()


def test_migration_created_audit_log_table(db_available):
    inspector = inspect(engine)
    assert "audit_log" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("audit_log")}
    assert {"id", "actor_id", "action", "entity", "entity_id", "details", "at"} <= columns


def test_record_audit_inserts_with_server_defaults(session):
    """id and at are populated by the DB; details round-trips as a dict."""
    db, created = session
    entry = record_audit(
        db,
        actor_id=None,
        action="seed",
        entity="staff_user",
        entity_id=uuid.uuid4(),
        details={"roles": ["dentist", "admin"]},
    )
    created.append(entry.id)
    db.commit()
    db.expire_all()

    fetched = db.get(AuditLog, entry.id)
    assert fetched is not None
    assert fetched.id is not None          # server-generated
    assert fetched.at is not None          # server-generated
    assert fetched.actor_id is None        # system action
    assert fetched.action == "seed"
    assert fetched.entity == "staff_user"
    assert fetched.details == {"roles": ["dentist", "admin"]}


def test_record_audit_with_actor_and_no_details(session):
    """actor_id set, details/entity_id omitted (nullable) works."""
    db, created = session
    actor = uuid.uuid4()
    entry = record_audit(db, actor_id=actor, action="update", entity="patient")
    created.append(entry.id)
    db.commit()
    db.expire_all()

    fetched = db.get(AuditLog, entry.id)
    assert fetched is not None
    assert fetched.actor_id == actor
    assert fetched.entity_id is None
    assert fetched.details is None
