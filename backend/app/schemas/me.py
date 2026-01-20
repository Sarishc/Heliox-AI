"""Schemas for /me endpoint."""
from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    team_id: str
    role: str
    feature_flags: dict = Field(default_factory=dict)
