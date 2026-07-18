"""Booking logic — double-booking detection.

Double-booking prevention lives in TWO places on purpose:

1. **The database** — a GiST EXCLUDE constraint (`appointment_no_overlap`) makes
   overlapping non-cancelled appointments for the same dentist physically
   impossible to store. This is the real guarantee: two clinic PCs racing to book
   the same slot cannot both succeed, because the constraint is enforced
   atomically at commit. See the migration.

2. **This service** — `find_conflicts()` runs the same overlap test in the
   application *before* inserting, so the common case returns a friendly 409 with
   a clear message instead of a raw constraint violation. It is a UX layer on top
   of the DB guarantee, NOT the guarantee itself.

The two use the same overlap definition so they always agree: half-open ranges
`[start, start + duration)` that intersect (`&&`), for the same dentist, ignoring
cancelled appointments. The range is built in UTC wall-clock (`timezone('UTC',
ts)` → plain timestamp, then `+ interval`) to mirror the constraint EXACTLY — see
the migration for why the constraint can't use `timestamptz + interval` directly.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Interval, cast, func, literal, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment


def _utc_range(start_time, duration_min):
    """A plain-timestamp half-open range [start, start+duration) in UTC.

    Mirrors the DB constraint's expression so the pre-check and the constraint
    agree on exactly which appointments overlap.
    """
    start_utc = func.timezone("UTC", start_time)
    end_utc = start_utc + (duration_min * cast(literal("1 minute"), Interval))
    return func.tsrange(start_utc, end_utc, "[)")


def find_conflicts(
    db: Session,
    *,
    dentist_id: UUID | None,
    start_time: datetime,
    duration_min: int,
    exclude_id: UUID | None = None,
) -> list[Appointment]:
    """Existing appointments that overlap the proposed slot for the same dentist.

    Returns [] when dentist_id is None: an unassigned booking never conflicts,
    matching the DB constraint's NULL semantics (NULLs are not `=` to each other).
    An empty list means "free to book".

    exclude_id skips a specific row — used when rescheduling so an appointment
    doesn't conflict with itself. Cancelled appointments are ignored (a cancelled
    slot frees the time).
    """
    # An unassigned slot is never a double-booking (there's no dentist to clash).
    if dentist_id is None:
        return []

    # The proposed slot's interval, and each existing appointment's — built the
    # same way as the DB constraint (UTC wall-clock plain-timestamp range).
    proposed = _utc_range(start_time, duration_min)
    existing = _utc_range(Appointment.start_time, Appointment.duration_min)

    stmt = (
        select(Appointment)
        .where(Appointment.dentist_id == dentist_id)
        .where(Appointment.status != "cancelled")
        .where(existing.op("&&")(proposed))  # ranges overlap
    )
    if exclude_id is not None:
        stmt = stmt.where(Appointment.id != exclude_id)

    return list(db.scalars(stmt).all())
