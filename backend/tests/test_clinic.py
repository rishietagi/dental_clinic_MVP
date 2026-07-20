"""Unit tests for the clinic-timezone service (step 4.9).

Pure logic, no DB — `clinic_day_bounds` is just date + zone arithmetic, so these
run everywhere. They pin the exact offset behaviour that fixes the UTC-day bug.
"""

from datetime import date, datetime, timezone

from app.services.clinic import clinic_day_bounds


def test_ist_day_maps_to_the_previous_utc_evening():
    """Asia/Kolkata is UTC+5:30 (no DST). 2 Aug clinic-local is
    1 Aug 18:30 UTC -> 2 Aug 18:29:59.999999 UTC."""
    start, end = clinic_day_bounds(date(2026, 8, 2), "Asia/Kolkata")

    assert start == datetime(2026, 8, 1, 18, 30, tzinfo=timezone.utc)
    assert end.astimezone(timezone.utc).replace(microsecond=0) == datetime(
        2026, 8, 2, 18, 29, 59, tzinfo=timezone.utc
    )
    # Both are tz-aware UTC.
    assert start.utcoffset().total_seconds() == 0
    assert end.utcoffset().total_seconds() == 0


def test_utc_day_is_plain_midnight_to_end_of_day():
    start, end = clinic_day_bounds(date(2026, 8, 2), "UTC")
    assert start == datetime(2026, 8, 2, 0, 0, tzinfo=timezone.utc)
    assert end.replace(microsecond=0) == datetime(
        2026, 8, 2, 23, 59, 59, tzinfo=timezone.utc
    )


def test_a_late_ist_instant_falls_in_the_right_clinic_day():
    """An appointment at 2 Aug 21:00 IST is stored at 2 Aug 15:30 UTC, which is
    inside 2 Aug's clinic bounds — the case the old UTC-day query got right — AND
    an appointment at 2 Aug 01:00 IST (1 Aug 19:30 UTC) is ALSO inside 2 Aug's
    clinic bounds, which the old UTC-day query got WRONG."""
    start, end = clinic_day_bounds(date(2026, 8, 2), "Asia/Kolkata")

    late_evening = datetime(2026, 8, 2, 15, 30, tzinfo=timezone.utc)   # 21:00 IST
    early_morning = datetime(2026, 8, 1, 19, 30, tzinfo=timezone.utc)  # 01:00 IST 2 Aug
    assert start <= late_evening <= end
    assert start <= early_morning <= end
