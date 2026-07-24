"""Practice reports — revenue trend, procedure mix, no-show rate (step 6.1).

The **eighth `services/` module.** Pure read aggregates for the owner's Reports
screen (BUILD_PLAN §6). Three questions:

- **Revenue trend** — how much was collected each month, last 6 months.
- **Procedure mix** — which procedures were billed most (by revenue), last 6 months.
- **No-show rate** — the share of scheduled appointments the patient didn't attend,
  last 30 days.

All time bucketing is in the **clinic timezone** (not UTC/server): a payment at 9pm
IST on the last of the month belongs to that month, not the next. We read the tz
from `clinic_settings` (the same source `list_appointments` and
`billing.todays_collections` use) and compute month/day windows in that zone. Money
is `Decimal`, quantized to cents (the 5.3 "0" vs "0.00" rule).

These are read-only and unaudited, like the other report/read endpoints.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.clinic_settings import ClinicSettings
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.payment import Payment
from app.models.staff_user import StaffUser
from app.models.treatment_item import TreatmentItem
from app.models.visit import Visit
from app.services.clinic import clinic_day_bounds

_CENTS = Decimal("0.01")

# Fold the procedure-mix tail past this many rows into "Other" (the dataviz rule —
# a long tail of tiny slices is noise, not signal).
_MIX_TOP_N = 8


def _cents(value) -> Decimal:
    return Decimal(value).quantize(_CENTS)


def _clinic_tz(db: Session) -> str:
    return db.get(ClinicSettings, 1).timezone


def _month_starts(today: date, months: int) -> list[date]:
    """The first-of-month dates for the last `months` months, oldest first,
    ending with the current month. E.g. months=6 in July -> Feb..Jul (1st of each)."""
    starts: list[date] = []
    y, m = today.year, today.month
    # Walk back months-1 steps from the current month, then reverse.
    for _ in range(months):
        starts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(starts))


def _month_bounds_utc(month_start: date, tz_name: str) -> tuple[datetime, datetime]:
    """UTC [start, end] window for a clinic-local calendar month.

    Reuses clinic_day_bounds: the month runs from 00:00 clinic-local on the 1st to
    the end of the last day of the month, in the clinic zone, expressed in UTC.
    """
    # Last day of this month = day before the 1st of next month.
    if month_start.month == 12:
        next_first = date(month_start.year + 1, 1, 1)
    else:
        next_first = date(month_start.year, month_start.month + 1, 1)
    last_day = date.fromordinal(next_first.toordinal() - 1)

    start, _ = clinic_day_bounds(month_start, tz_name)
    _, end = clinic_day_bounds(last_day, tz_name)
    return start, end


def revenue_trend(db: Session, months: int = 6, dentist_id=None) -> list[dict]:
    """Collected revenue per clinic-month for the last `months` months.

    Every month in the window is present, including zero months, so the trend line
    has no gaps. `month` is a `YYYY-MM` string; `total` is a quantized Decimal.
    When `dentist_id` is given, only payments on invoices whose visit's PRIMARY
    dentist is that dentist are counted (attribution = the visit's dentist).
    """
    tz_name = _clinic_tz(db)
    today = datetime.now(ZoneInfo(tz_name)).date()
    out: list[dict] = []
    for ms in _month_starts(today, months):
        start, end = _month_bounds_utc(ms, tz_name)
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.paid_at >= start, Payment.paid_at <= end
        )
        if dentist_id is not None:
            stmt = (
                stmt.join(Invoice, Payment.invoice_id == Invoice.id)
                .join(Visit, Invoice.visit_id == Visit.id)
                .where(Visit.dentist_id == dentist_id)
            )
        total = db.scalar(stmt)
        out.append({"month": f"{ms.year:04d}-{ms.month:02d}", "total": _cents(total)})
    return out


def procedure_mix(db: Session, months: int = 6, dentist_id=None) -> list[dict]:
    """Billed procedures over the last `months`, grouped by catalogue item.

    Groups **invoice_line** (the frozen record of what was charged) by
    `treatment_item_id`, joined to the item name; counts lines and sums amounts,
    ordered by revenue. The tail past _MIX_TOP_N folds into an "Other" row.
    Custom lines (null treatment_item_id) group under "Other / custom".
    """
    tz_name = _clinic_tz(db)
    today = datetime.now(ZoneInfo(tz_name)).date()
    window_start, _ = _month_bounds_utc(_month_starts(today, months)[0], tz_name)
    _, window_end = _month_bounds_utc(_month_starts(today, months)[-1], tz_name)

    stmt = (
        select(
            TreatmentItem.name,
            func.count(InvoiceLine.id),
            func.coalesce(func.sum(InvoiceLine.amount), 0),
        )
        .select_from(InvoiceLine)
        .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .outerjoin(TreatmentItem, InvoiceLine.treatment_item_id == TreatmentItem.id)
        .where(Invoice.created_at >= window_start, Invoice.created_at <= window_end)
        .group_by(TreatmentItem.name)
    )
    if dentist_id is not None:
        stmt = stmt.join(Visit, Invoice.visit_id == Visit.id).where(
            Visit.dentist_id == dentist_id
        )
    rows = db.execute(stmt).all()

    # name is None for custom lines (no catalogue link) — label them.
    items = [
        {"name": name or "Other / custom", "count": count, "revenue": _cents(revenue)}
        for name, count, revenue in rows
    ]
    items.sort(key=lambda r: r["revenue"], reverse=True)

    if len(items) <= _MIX_TOP_N:
        return items

    head = items[:_MIX_TOP_N]
    tail = items[_MIX_TOP_N:]
    other = {
        "name": "Other",
        "count": sum(r["count"] for r in tail),
        "revenue": _cents(sum((r["revenue"] for r in tail), Decimal("0"))),
    }
    return head + [other]


def no_show_rate(db: Session, days: int = 30, dentist_id=None) -> dict:
    """No-show rate over the last `days` clinic-days.

    Denominator is scheduled appointments that were NOT cancelled
    (booked/arrived/done/no_show) — a cancellation isn't a no-show, so it doesn't
    count against attendance. Rate is a percentage (0-100), quantized to 1 decimal.
    A period with no appointments returns rate 0 (never a divide-by-zero). When
    `dentist_id` is given, only that dentist's appointments count.
    """
    tz_name = _clinic_tz(db)
    today = datetime.now(ZoneInfo(tz_name)).date()
    # `days` clinic-days back, inclusive of today: start of (today - (days-1)).
    first_day = date.fromordinal(today.toordinal() - (days - 1))
    start, _ = clinic_day_bounds(first_day, tz_name)
    _, end = clinic_day_bounds(today, tz_name)

    in_window = (Appointment.start_time >= start) & (Appointment.start_time <= end)
    stmt = (
        select(Appointment.status, func.count(Appointment.id))
        .where(in_window)
        .group_by(Appointment.status)
    )
    if dentist_id is not None:
        stmt = stmt.where(Appointment.dentist_id == dentist_id)
    counts = dict(db.execute(stmt).all())

    no_show = counts.get("no_show", 0)
    done = counts.get("done", 0)
    cancelled = counts.get("cancelled", 0)
    total = sum(counts.values())

    # Attendance denominator excludes cancellations. Rate as a percentage, 1 dp.
    scheduled = total - cancelled
    rate = round(no_show / scheduled * 100, 1) if scheduled else 0.0

    return {
        "total": total,
        "no_show": no_show,
        "done": done,
        "cancelled": cancelled,
        "rate": rate,
    }


def revenue_by_dentist(db: Session, months: int = 6) -> list[dict]:
    """Revenue collected + visits recorded per dentist over the last `months`.

    Attribution is the **visit's primary dentist** (how visits are recorded).
    Revenue = payments on that visit's invoice, in the window; visits = distinct
    visits in the window. Payments/visits with no attributable dentist fold into an
    "Unassigned" row. Ordered by revenue desc. Money is quantized Decimal.
    """
    tz_name = _clinic_tz(db)
    today = datetime.now(ZoneInfo(tz_name)).date()
    window_start, _ = _month_bounds_utc(_month_starts(today, months)[0], tz_name)
    _, window_end = _month_bounds_utc(_month_starts(today, months)[-1], tz_name)

    # Revenue per dentist: sum payments joined through invoice -> visit -> dentist.
    rev_rows = db.execute(
        select(
            Visit.dentist_id,
            StaffUser.name,
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .select_from(Payment)
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(Visit, Invoice.visit_id == Visit.id)
        .outerjoin(StaffUser, Visit.dentist_id == StaffUser.id)
        .where(Payment.paid_at >= window_start, Payment.paid_at <= window_end)
        .group_by(Visit.dentist_id, StaffUser.name)
    ).all()

    # Visit counts per dentist in the window (by visit_date).
    visit_rows = db.execute(
        select(Visit.dentist_id, func.count(Visit.id))
        .where(Visit.visit_date >= window_start, Visit.visit_date <= window_end)
        .group_by(Visit.dentist_id)
    ).all()
    visits_by = {did: count for did, count in visit_rows}

    by: dict = {}
    for did, name, revenue in rev_rows:
        key = str(did) if did else None
        by[key] = {
            "dentist_id": str(did) if did else None,
            "dentist_name": name or "Unassigned",
            "revenue": _cents(revenue),
            "visits": visits_by.get(did, 0),
        }
    # Include dentists who have visits but no payments yet.
    for did, count in visit_rows:
        key = str(did) if did else None
        if key not in by:
            who = db.get(StaffUser, did) if did else None
            by[key] = {
                "dentist_id": str(did) if did else None,
                "dentist_name": who.name if who else "Unassigned",
                "revenue": _cents(0),
                "visits": count,
            }

    rows = list(by.values())
    rows.sort(key=lambda r: r["revenue"], reverse=True)
    return rows
