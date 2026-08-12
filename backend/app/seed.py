"""Seed the clinic's staff_user rows from environment variables.

Run once per environment (safe to re-run — every row is an idempotent upsert):

    python -m app.seed

Supabase Auth holds the credentials; this creates the matching rows in our
staff_user table with the roles that authorize what each login can do. **A row's
primary key IS that user's Supabase Auth UUID**, so step 1.3 can map a verified
JWT (its `sub`) straight to the row. Copy the UUID from the Supabase dashboard →
Authentication → Users. Get it wrong and the login authenticates but is rejected
as "not an active staff member".

THREE LOGINS (6.12). The clinic used to run one shared login; the owner asked for
one account per role so that the practice's money sits behind the admin login only:

    ADMIN        ["dentist", "admin"]   the owner — sees everything, incl. reports
                                        and the dashboard's day total
    DENTIST      ["dentist"]            clinical work; NO reports, NO day total
    RECEPTIONIST ["receptionist"]       front desk; bills patients, but NO reports
                                        and NO day total

Note the admin keeps BOTH roles: she is one person who is dentist and admin, and
must not have to log in twice (BUILD_PLAN §2). That is the canonical
roles-as-a-set case, and it is why `roles` is an array rather than a string.

These are SHARED ROLE accounts, not one per person — every dentist signs in as the
same `dentist` user. Which dentist actually treated a patient is recorded by the
dentist dropdown on the appointment/visit, exactly as before (6.5: dentists are
name-only records, not logins).

Env vars (see .env.example):
  ADMIN_USER_ID / ADMIN_EMAIL / ADMIN_NAME                  — REQUIRED
  DENTIST_USER_ID / DENTIST_EMAIL / DENTIST_NAME            — optional
  RECEPTION_USER_ID / RECEPTION_EMAIL / RECEPTION_NAME      — optional

The two optional accounts are skipped silently when unset, so an environment that
predates 6.12 (or a dev box that only needs the admin) keeps working unchanged.
"""

import os
import sys
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.staff_user import StaffUser
from app.services.audit import record_audit

# The owner is both dentist and admin under one login — the canonical
# roles-as-a-set case.
ADMIN_ROLES = ["dentist", "admin"]
DENTIST_ROLES = ["dentist"]
RECEPTION_ROLES = ["receptionist"]


def _require(name: str) -> str:
    """Read a required env var, failing loud (not silent) if it's missing/empty."""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(
            f"error: {name} is not set. Set ADMIN_USER_ID / ADMIN_EMAIL / "
            f"ADMIN_NAME (see .env.example) before seeding."
        )
    return value


def _optional(name: str) -> str | None:
    """Read an optional env var. Empty or unset both mean 'not configured'."""
    return os.environ.get(name, "").strip() or None


def _upsert(session: Session, staff_id: UUID, name: str, email: str, roles: list[str]) -> str:
    """Create or update one staff row + its audit entry. Returns what it did.

    Written into the caller's session so the upsert and its audit row commit
    together — the same pattern every write in this codebase follows.
    """
    existing = session.get(StaffUser, staff_id)
    if existing is None:
        session.add(
            StaffUser(id=staff_id, name=name, email=email, roles=roles, active=True)
        )
        action = "created"
    else:
        existing.name = name
        existing.email = email
        existing.roles = roles
        existing.active = True
        action = "updated"

    # Record the seed as a system action (no logged-in actor).
    record_audit(
        session,
        actor_id=None,
        action="seed",
        entity="staff_user",
        entity_id=staff_id,
        details={"result": action, "roles": roles},
    )
    return action


def _seed_optional(
    session: Session, label: str, prefix: str, roles: list[str]
) -> str | None:
    """Seed one of the optional role logins, if its env vars are set.

    All three vars must be present together: a half-configured account (an id but
    no email, say) is a mistake worth failing on rather than guessing past.
    """
    raw_id = _optional(f"{prefix}_USER_ID")
    email = _optional(f"{prefix}_EMAIL")
    name = _optional(f"{prefix}_NAME")

    if raw_id is None and email is None and name is None:
        return None  # not configured at all — fine, skip it

    if not (raw_id and email and name):
        sys.exit(
            f"error: {label} is half-configured. Set all three of "
            f"{prefix}_USER_ID / {prefix}_EMAIL / {prefix}_NAME, or none of them."
        )

    try:
        staff_id = UUID(raw_id)
    except ValueError:
        sys.exit(
            f"error: {prefix}_USER_ID is not a valid UUID. Copy it from the "
            f"Supabase dashboard → Authentication → Users."
        )

    action = _upsert(session, staff_id, name, email, roles)
    print(f"seed: {label} {action} — {email} ({staff_id}) roles={roles}")
    return action


def seed_admin() -> None:
    """Seed the admin, plus the dentist and receptionist logins if configured."""
    admin_id = UUID(_require("ADMIN_USER_ID"))
    email = _require("ADMIN_EMAIL")
    name = _require("ADMIN_NAME")

    with SessionLocal() as session:
        action = _upsert(session, admin_id, name, email, ADMIN_ROLES)
        print(f"seed: admin {action} — {email} ({admin_id}) roles={ADMIN_ROLES}")

        seeded = [
            _seed_optional(session, "dentist", "DENTIST", DENTIST_ROLES),
            _seed_optional(session, "receptionist", "RECEPTION", RECEPTION_ROLES),
        ]
        session.commit()

    skipped = sum(1 for s in seeded if s is None)
    if skipped:
        print(
            f"seed: {skipped} optional login(s) not configured — set "
            f"DENTIST_* / RECEPTION_* in .env to create them (see .env.example)."
        )
    print("seed: audit_log entries written (action=seed, entity=staff_user)")


if __name__ == "__main__":
    seed_admin()
