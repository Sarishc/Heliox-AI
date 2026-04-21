"""Team schemas for request/response validation."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class TeamBase(BaseModel):
    """Base team schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique name of the team")
    monthly_budget_usd: Optional[float] = Field(None, gt=0, description="Monthly infra budget in USD")


class TeamCreate(TeamBase):
    """Schema for creating a new team."""

    pass


class TeamUpdate(BaseModel):
    """Schema for updating a team. OWASP: extra='forbid' prevents mass assignment."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Updated team name")
    monthly_budget_usd: Optional[float] = Field(None, gt=0, description="Monthly infra budget in USD")


class Team(TeamBase):
    """Schema for team responses."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamBudgetUpdate(BaseModel):
    """Schema for updating team budget. OWASP: extra='forbid'."""

    model_config = ConfigDict(extra="forbid")

    monthly_budget_usd: float = Field(..., gt=0, description="Monthly infra budget in USD")
