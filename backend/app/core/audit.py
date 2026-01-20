"""Audit logging helpers."""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit_event(
    db: Session,
    *,
    team_id: UUID,
    actor_type: str,
    actor_id: Optional[str],
    action: str,
    metadata: Optional[dict] = None
) -> None:
    log = AuditLog(
        team_id=team_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        event_metadata=metadata or {}
    )
    db.add(log)
    db.commit()
