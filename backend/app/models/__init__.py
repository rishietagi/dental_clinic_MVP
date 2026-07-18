"""SQLAlchemy declarative base.

Every model inherits from Base. Base.metadata is the in-code description of all
tables — Alembic compares it against the live database to generate migrations.
No models exist yet (Phase 2); Base.metadata is intentionally empty for now.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
