"""The lab model — the outside dental labs this clinic sends work to (step 6.6).

A small vendor list: crowns, bridges and dentures are made by an external lab, and
the clinic deals with a handful of them repeatedly. Storing them (rather than typing
the lab's name on every case) is the same instinct as the treatment catalogue (4.1):
a typo'd name ("Sri Dental Lab" vs "sri dental lab") would fragment the data and make
any per-lab view meaningless, and picking from a dropdown is faster for the
receptionist than typing.

`name` is unique for exactly that reason. **Deactivate, never delete** — a retired
lab must still resolve, or a two-year-old lab case becomes unreadable (same rule as
treatment items and patients).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class Lab(Base):
    __tablename__ = "lab"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Unique — duplicates would fragment per-lab data. Indexed for the picker.
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)

    # Who to call when a case is late. Free text (formatting, +91, etc.).
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft-deactivate. Never hard-delete: historical lab cases must keep resolving.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Lab {self.name}{'' if self.active else ' [inactive]'}>"
