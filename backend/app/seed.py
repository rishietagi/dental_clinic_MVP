"""Seed the single local staff row (step 10.1 — there is no login any more).

Run once per install, and safe to re-run (idempotent upsert):

    python -m app.seed

WHAT THIS IS FOR
    The app has no authentication: it is a packaged desktop app used by one
    person at a time on one PC. But every write is still ATTRIBUTED to a staff
    member — `audit_log.actor_id`, `visit.dentist_id`, `appointment.dentist_id`
    — so exactly one `staff_user` row has to exist for those to point at.

    That row's id is fixed (`LOCAL_STAFF_ID`, see app/config.py) rather than
    random, so it survives a reseed and a reinstall. If it moved, every existing
    audit row and visit would point at a staff member that no longer exists.

    It holds BOTH roles (`["dentist", "admin"]`) because there is nobody to
    distinguish. `require_role` is a no-op since 10.1 — the roles are kept
    populated so the column stays meaningful, and so restoring real role
    enforcement later needs no data migration.

HISTORY
    Until 10.1 this seeded three Supabase-backed logins (admin / dentist /
    receptionist, step 6.12) from ADMIN_* / DENTIST_* / RECEPTION_* env vars,
    each row's primary key being that user's Supabase Auth UUID. All of that is
    gone with the login screen.
"""

from app.config import settings
from app.db import SessionLocal
from app.models.staff_user import StaffUser
from app.services.audit import record_audit

# Both roles: there is one user and nothing to gate them out of.
LOCAL_ROLES = ["dentist", "admin"]


def seed_local_staff() -> None:
    """Create or update the one staff row the whole app is attributed to."""
    from uuid import UUID

    try:
        staff_id = UUID(settings.local_staff_id)
    except ValueError:
        raise SystemExit(
            f"error: LOCAL_STAFF_ID is not a valid UUID: {settings.local_staff_id!r}"
        )

    email = settings.local_staff_email
    name = settings.local_staff_name

    with SessionLocal() as session:
        existing = session.get(StaffUser, staff_id)
        if existing is None:
            session.add(
                StaffUser(
                    id=staff_id,
                    name=name,
                    email=email,
                    roles=LOCAL_ROLES,
                    active=True,
                )
            )
            action = "created"
        else:
            # Never change the id — only the display fields. Re-activating is
            # deliberate: a deactivated local row would lock the whole app out.
            existing.name = name
            existing.email = email
            existing.roles = LOCAL_ROLES
            existing.active = True
            action = "updated"

        # Recorded as a system action (no logged-in actor), committed in the same
        # transaction as the upsert.
        record_audit(
            session,
            actor_id=None,
            action="seed",
            entity="staff_user",
            entity_id=staff_id,
            details={"result": action, "roles": LOCAL_ROLES},
        )
        session.commit()

    print(f"seed: local staff {action} — {email} ({staff_id}) roles={LOCAL_ROLES}")
    print("seed: audit_log entry written (action=seed, entity=staff_user)")


# Kept as an alias so anything that still calls the old name keeps working.
seed_admin = seed_local_staff


if __name__ == "__main__":
    seed_local_staff()
