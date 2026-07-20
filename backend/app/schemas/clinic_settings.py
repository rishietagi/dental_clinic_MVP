"""Clinic-settings request/response schemas (step 4.9).

The read carries the whole settings row. The update is a PATCH (all optional),
with validation that keeps the row sane before it ever reaches the DB CHECKs:

- `timezone` must be a real IANA zone (constructing `ZoneInfo` succeeds), else
  422 — a typo'd zone would silently break day-boundary math.
- hours are 0–23 / 1–24 and `close_hour > open_hour`. The single-field bounds
  are checked here; the cross-field `close > open` is re-checked in the router
  against the MERGED row (a PATCH may set only one of the two).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except Exception as exc:  # noqa: BLE001 — any failure means "not a real zone"
        raise ValueError(f"'{value}' is not a valid IANA timezone.") from exc
    return value


class ClinicSettingsRead(BaseModel):
    """The clinic's configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    open_hour: int
    close_hour: int
    slot_minutes: int
    timezone: str
    updated_at: datetime


class ClinicSettingsUpdate(BaseModel):
    """Partial update. Cross-field close>open is enforced in the router against
    the merged row, since a PATCH may touch only one hour."""

    open_hour: int | None = Field(default=None, ge=0, le=23)
    close_hour: int | None = Field(default=None, ge=1, le=24)
    slot_minutes: int | None = Field(default=None, gt=0)
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        return _valid_timezone(v) if v is not None else v
