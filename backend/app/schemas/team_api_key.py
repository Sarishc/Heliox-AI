"""Schemas for team API keys."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TeamAPIKeyCreate(BaseModel):
    """Schema for creating a team API key."""
    
    key_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name for this API key"
    )
    team_id: str = Field(
        ...,
        description="Team ID that will own this API key"
    )


class TeamAPIKeyResponse(BaseModel):
    """Schema for team API key response (without sensitive data)."""
    
    id: UUID
    team_id: str
    key_name: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class TeamAPIKeyCreateResponse(BaseModel):
    """Schema for API key creation response (includes the key once)."""
    
    id: UUID
    team_id: str
    key_name: str
    api_key: str = Field(
        ...,
        description="The API key value (only shown once on creation)"
    )
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
