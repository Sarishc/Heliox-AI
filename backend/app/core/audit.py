"""Audit logging helpers."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def record_cross_tenant_attempt(
    *,
    resource_type: str,
    resource_id: str,
    requested_team_id: UUID,
    actual_team_id: UUID,
    actor_id: Optional[str] = None,
) -> None:
    """
    Log cross-tenant access attempt for security monitoring.
    Does not require DB - logs to application logger.
    """
    logger.warning(
        "Cross-tenant access attempt blocked",
        extra={
            "resource_type": resource_type,
            "resource_id": resource_id,
            "requested_team_id": str(requested_team_id),
            "actual_team_id": str(actual_team_id),
            "actor_id": actor_id,
        },
    )


def record_audit_event(
    db: Session,
    *,
    team_id: UUID,
    actor_type: str,
    actor_id: Optional[str],
    action: str,
    metadata: Optional[dict] = None,
) -> None:
    log = AuditLog(
        team_id=team_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        event_metadata=metadata or {},
    )
    db.add(log)
    db.commit()
