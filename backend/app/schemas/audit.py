"""Schemas for audit logs."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    id: UUID
    team_id: UUID
    actor_type: str
    actor_id: Optional[str] = None
    action: str
    metadata: dict = Field(
        validation_alias="event_metadata",
        serialization_alias="metadata"
    )
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
