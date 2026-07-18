"""SQLAlchemy declarative base.

Every model inherits from Base. Base.metadata is the in-code description of all
tables — Alembic compares it against the live database to generate migrations.

Models must be IMPORTED here so they register on Base.metadata by the time
Alembic's env.py runs; otherwise --autogenerate sees an empty schema. Import them
at the bottom (after Base is defined) to avoid a circular import.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Register models on Base.metadata. Keep after Base so the modules can import it.
from app.models.staff_user import StaffUser  # noqa: E402,F401
from app.models.audit_log import AuditLog  # noqa: E402,F401
from app.models.patient import Patient  # noqa: E402,F401
