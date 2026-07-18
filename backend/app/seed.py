"""Seed the admin staff_user row from environment variables.

Run once per environment (safe to re-run — it's an idempotent upsert):

    python -m app.seed

Supabase Auth holds the admin's credentials; this creates the matching row in
our staff_user table with the roles that authorize what they can do. The row's
primary key is the admin's Supabase Auth UUID, so step 1.3 can map a verified
JWT (its `sub`) straight to this row.

Required env vars (see .env.example):
  ADMIN_USER_ID  — the admin's Supabase Auth UUID
                   (Supabase dashboard → Authentication → Users → the user)
  ADMIN_EMAIL    — their login email
  ADMIN_NAME     — display name
"""

import os
import sys
from uuid import UUID

from app.db import SessionLocal
from app.models.staff_user import StaffUser
from app.services.audit import record_audit

# The mother is both dentist and admin under one login — the canonical
# roles-as-a-set case. Receptionists would get ["receptionist"].
ADMIN_ROLES = ["dentist", "admin"]


def _require(name: str) -> str:
    """Read a required env var, failing loud (not silent) if it's missing/empty."""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(
            f"error: {name} is not set. Set ADMIN_USER_ID / ADMIN_EMAIL / "
            f"ADMIN_NAME (see .env.example) before seeding."
        )
    return value


def seed_admin() -> None:
    admin_id = UUID(_require("ADMIN_USER_ID"))
    email = _require("ADMIN_EMAIL")
    name = _require("ADMIN_NAME")

    with SessionLocal() as session:
        existing = session.get(StaffUser, admin_id)
        if existing is None:
            session.add(
                StaffUser(
                    id=admin_id,
                    name=name,
                    email=email,
                    roles=ADMIN_ROLES,
                    active=True,
                )
            )
            action = "created"
        else:
            existing.name = name
            existing.email = email
            existing.roles = ADMIN_ROLES
            existing.active = True
            action = "updated"

        # Record the seed as a system action (no logged-in actor). Written in the
        # same session so it commits atomically with the upsert above.
        record_audit(
            session,
            actor_id=None,
            action="seed",
            entity="staff_user",
            entity_id=admin_id,
            details={"result": action, "roles": ADMIN_ROLES},
        )
        session.commit()

    print(f"seed: admin {action} — {email} ({admin_id}) roles={ADMIN_ROLES}")
    print(f"seed: audit_log entry written (action=seed, entity=staff_user)")


if __name__ == "__main__":
    seed_admin()
