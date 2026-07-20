"""The clinic_settings model — a single row of clinic-wide configuration.

There is exactly one clinic (BUILD_PLAN: a single small dental clinic), so this
is a **singleton table**: one row, pinned to `id = 1` by a CHECK constraint. That
is the simplest possible "there can be only one" guarantee — every reader does
`db.get(ClinicSettings, 1)` and every write targets that row.

It holds the two things that were hardcoded through Phase 3–4 and are now
configurable:

- **Clinic hours + slot size** (`open_hour`, `close_hour`, `slot_minutes`) — the
  week-view calendar grid and the visit form's follow-up duration read these
  instead of the constants that used to live in `frontend/lib/week.ts`.
- **Timezone** (`timezone`, an IANA name like `Asia/Kolkata`) — the load-bearing
  one. The appointments day/range query bounds "a day" in this zone (not UTC),
  and the frontend renders times in it. Before this, "a day" was a UTC day; an
  IST evening slot could fall on the wrong UTC date.

The CHECK constraints (`id = 1`, `close_hour > open_hour`, sane ranges) are added
by hand in the migration — Alembic autogenerate doesn't emit them.
"""

from datetime import datetime

from sqlalchemy import Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class ClinicSettings(Base):
    __tablename__ = "clinic_settings"

    # Pinned to 1 by a CHECK in the migration — the singleton guarantee. Not
    # server-generated: the migration inserts the one row with id=1.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    # Clinic day window, as whole hours 0–23. close_hour is the exclusive upper
    # bound of the last slot's start (matches the old DAY_END_HOUR semantics).
    open_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="9")
    close_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default="18")

    # Appointment slot granularity in minutes.
    slot_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="30"
    )

    # IANA timezone name (e.g. "Asia/Kolkata"). Validated as a real zone in the
    # schema layer; stored as free text.
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="Asia/Kolkata"
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<ClinicSettings {self.open_hour:02d}:00-{self.close_hour:02d}:00 "
            f"/{self.slot_minutes}m {self.timezone}>"
        )
