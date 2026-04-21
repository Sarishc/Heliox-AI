"""Schemas for team membership and roles."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models.team_member import TeamRole


class TeamMemberCreate(BaseModel):
    team_id: UUID = Field(..., description="Team ID")
    user_id: UUID = Field(..., description="User ID")
    role: TeamRole = Field(default=TeamRole.VIEWER)


class TeamMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: TeamRole = Field(..., description="Updated role")


class TeamMemberResponse(BaseModel):
    id: UUID
    team_id: UUID
    user_id: UUID
    role: TeamRole
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
