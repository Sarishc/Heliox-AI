"""Schemas for team invitations."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models.team_member import TeamRole


class TeamInviteCreate(BaseModel):
    """Create a team invite."""

    email: EmailStr = Field(..., description="Email to invite")
    role: TeamRole = Field(default=TeamRole.VIEWER, description="Role to assign on accept")


class TeamInviteResponse(BaseModel):
    """Response for a team invite (no token)."""

    id: UUID
    team_id: UUID
    email: str
    role: str
    invited_by_user_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    invite_link: str | None = None  # Only set on create

    model_config = ConfigDict(from_attributes=True)


class TeamInviteCreateResponse(BaseModel):
    """Response when creating an invite (includes one-time link)."""

    id: UUID
    team_id: UUID
    email: str
    role: str
    expires_at: datetime
    invite_link: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InviteValidateResponse(BaseModel):
    """Public info returned when validating an invite token."""

    valid: bool = True
    team_name: str
    team_id: UUID
    email: str
    role: str
    expires_at: datetime
    inviter_name: str | None = None


class InviteAcceptBody(BaseModel):
    """Body for accepting an invite (email required for verification)."""

    email: EmailStr = Field(..., description="Must match invite email")
    password: str | None = Field(None, min_length=8, max_length=72, description="Required for new user signup")
    full_name: str | None = Field(None, max_length=255, description="Optional for new user signup")
