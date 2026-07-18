"""Write audit-log entries.

The single way anything records "who changed what". Phase 2+ mutation endpoints
call record_audit() inside their own transaction, so the audit row and the change
it describes commit together (or roll back together).
"""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit(
    db: Session,
    *,
    actor_id: UUID | None,
    action: str,
    entity: str,
    entity_id: UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Insert one audit row into the caller's transaction.

    Does NOT commit — the caller owns the transaction, so the audit entry lands
    atomically with the change being audited. Pass actor_id=None for system
    actions with no logged-in user (e.g. the seed).

    Returns the flushed AuditLog (so id/at are populated if the caller needs them).
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    db.flush()  # populate server defaults (id, at) without committing
    return entry
