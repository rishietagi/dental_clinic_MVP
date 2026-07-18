"""add appointment no-overlap constraint

Revision ID: feae714ecef5
Revises: 56fda58b828c
Create Date: 2026-07-18 23:38:45.871466

Double-booking prevention at the storage layer. This is the FIRST hand-written
migration in the project: Alembic's --autogenerate cannot express an EXCLUDE
constraint or a CREATE EXTENSION, so the body is raw SQL via op.execute().

The constraint makes it physically impossible to store two overlapping,
non-cancelled appointments for the SAME dentist — the guarantee that survives two
clinic PCs racing to book the same slot (BUILD_PLAN §11). Overlap uses half-open
ranges [start, start + duration_min) so back-to-back slots (10:00-10:30 and
10:30-11:00) do NOT clash.

Notes:
- `btree_gist` lets a uuid `=` operator share a GiST index with the range `&&`.
- The end of the slot is computed in IMMUTABLE arithmetic. `timestamptz + interval`
  is only STABLE (it depends on the session TimeZone), and Postgres refuses a
  non-immutable function inside an index/constraint expression. The fix:
  `timezone('UTC', start_time)` casts to a plain `timestamp` at a FIXED zone
  (immutable), and `timestamp + interval` IS immutable — so we build a plain
  `tsrange` in UTC wall-clock. Two appointments overlap in real time iff their
  UTC representations overlap, so this is equivalent and correct.
- NULL dentist_id rows don't clash with each other (WITH = treats NULLs as
  distinct), so unassigned bookings never conflict until a dentist is set.
- Cancelled appointments are excluded, so a cancelled slot frees its time. (No
  cancel endpoint exists yet — that's 3.5 — but building the WHERE clause now
  means 3.5 needs no migration change.)
- The app-side pre-check in app/services/appointments.py MUST use this exact same
  expression so the friendly 409 and this backstop always agree.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'feae714ecef5'
down_revision: Union[str, Sequence[str], None] = '56fda58b828c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE appointment
        ADD CONSTRAINT appointment_no_overlap
        EXCLUDE USING gist (
            dentist_id WITH =,
            tsrange(
                timezone('UTC', start_time),
                timezone('UTC', start_time) + (duration_min * interval '1 minute'),
                '[)'
            ) WITH &&
        )
        WHERE (status <> 'cancelled')
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE appointment DROP CONSTRAINT appointment_no_overlap")
    # Drop the extension too — nothing else uses it, so downgrade is fully clean.
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
