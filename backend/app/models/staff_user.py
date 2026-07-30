"""The staff_user model — one row per staff member (dentist, receptionist, admin).

Supabase Auth owns credentials (email/password, sessions). This table owns
*authorization* — which roles a person holds — plus a little staff profile data.

The primary key IS the Supabase Auth user's UUID (the JWT `sub`). One identity,
no separate linking column: step 1.3 will verify a JWT, read `sub`, and look the
row up by primary key to get the roles.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Numeric, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class StaffUser(Base):
    __tablename__ = "staff_user"

    __table_args__ = (
        CheckConstraint(
            "consultation_fee IS NULL OR consultation_fee >= 0",
            name="ck_staff_user_consultation_fee_non_negative",
        ),
    )

    # Not server-generated: this is the Supabase Auth user's UUID, set on insert.
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)

    name: Mapped[str] = mapped_column(String, nullable=False)

    # Mirrors the Supabase login email — convenient for lookups/joins. Supabase
    # remains the source of truth for authentication itself.
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    # A SET of roles, e.g. ["dentist", "admin"]. Never a single role string — the
    # mother is both dentist and admin under one login. Postgres-native text array.
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )

    # Deactivate a staff login without deleting the row.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # What this dentist charges for a consultation (6.7). MONEY -> Numeric, never
    # float (the 4.1 rule).
    #
    # NULLABLE ON PURPOSE: null means "no fee set" and the visit screen offers
    # nothing, which is a different statement from a deliberate 0.00 ("this
    # dentist doesn't charge"). A receptionist must never be shown a ₹0
    # consultation just because nobody has filled the field in yet.
    #
    # The fee is NOT a treatment_item: it is per-dentist, so it reaches an
    # invoice as a custom line rather than through the catalogue pipeline.
    consultation_fee: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<StaffUser {self.email} roles={self.roles}>"
