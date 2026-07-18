"""The audit_log model — an append-only record of who changed what, and when.

A non-negotiable for health data (BUILD_PLAN §11). Every mutation in Phase 2+
writes one row here via app.services.audit.record_audit().

Design notes:
- `actor_id` is nullable with NO foreign key. Null = a system action (e.g. the
  seed) with no logged-in user. No FK because an audit trail must OUTLIVE the
  entities it references — deleting a staff member must never remove or block
  their history.
- `details` (JSONB) is a deliberate extension beyond the ERD, to capture context
  (e.g. what changed) without a column per case. Nullable.
- Rows are append-only: the service only ever inserts.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import Text, TIMESTAMP

from app.models import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    # Server-generated — audit ids are internal, unlike staff_user's external UUID.
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # The staff_user who acted; NULL for system/seed actions. No FK on purpose.
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    # What happened, and to which kind of thing: e.g. action="create",
    # entity="patient". Free-form strings kept deliberately simple.
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)

    # The affected row's id. Nullable — some actions have no single target.
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    # Free-form context, e.g. {"roles": ["dentist", "admin"]}. Nullable.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity} actor={self.actor_id}>"
