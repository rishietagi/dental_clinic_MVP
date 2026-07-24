"""Practice-report response schemas (step 6.1).

One `ReportsResponse` bundles all three reports so the screen fetches once. Money
is `Decimal` (serialized as strings, exact — the 4.1 rule); the no-show rate is a
plain float percentage (0-100).
"""

from decimal import Decimal

from pydantic import BaseModel


class RevenuePoint(BaseModel):
    """One month of collected revenue. `month` is 'YYYY-MM'."""

    month: str
    total: Decimal


class ProcedureMixRow(BaseModel):
    """One procedure's billed volume + revenue over the window."""

    name: str
    count: int
    revenue: Decimal


class NoShowSummary(BaseModel):
    """No-show counts + rate over the window. `rate` is a percentage (0-100)."""

    total: int
    no_show: int
    done: int
    cancelled: int
    rate: float


class DentistRevenueRow(BaseModel):
    """One dentist's revenue + visit count over the window (6.5)."""

    dentist_id: str | None
    dentist_name: str
    revenue: Decimal
    visits: int


class ReportsResponse(BaseModel):
    """Everything the Reports screen needs, in one payload."""

    revenue_trend: list[RevenuePoint]
    procedure_mix: list[ProcedureMixRow]
    no_show: NoShowSummary
    by_dentist: list[DentistRevenueRow]
