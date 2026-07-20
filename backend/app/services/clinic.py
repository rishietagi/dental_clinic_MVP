"""Clinic-timezone helpers (step 4.9) — the fifth `services/` module.

The load-bearing fix of the Phase-4 wrap. Before this, `list_appointments`
bounded "a day" in **UTC**: `datetime.combine(date, time.min, tzinfo=utc)`. For a
clinic in IST that's wrong — "2 August" at the clinic runs from
`2 Aug 00:00 IST` to `2 Aug 23:59 IST`, which in UTC is
`1 Aug 18:30 → 2 Aug 18:29`. An evening appointment on 2 Aug IST is stored at an
instant that is *1 Aug* in UTC, so the old UTC-day query missed it.

`clinic_day_bounds` computes the correct UTC half-open-ish window [start, end]
for a clinic-local calendar day, given the clinic's IANA timezone. The overlap
constraint and `find_conflicts` are unaffected — they compare instants, which
are zone-independent; only "which calendar day is this instant in" needed fixing.
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def clinic_day_bounds(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """UTC bounds of a clinic-local calendar day.

    Returns (start_utc, end_utc) where start is clinic-local 00:00:00.000000 and
    end is clinic-local 23:59:59.999999 on `day`, both converted to UTC. The
    caller uses them as inclusive bounds (`start_time >= start AND <= end`),
    matching the previous query's shape.
    """
    tz = ZoneInfo(tz_name)
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = datetime.combine(day, time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
