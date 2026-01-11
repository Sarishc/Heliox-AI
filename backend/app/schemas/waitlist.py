"\"\"\"Schemas for waitlist signups.\"\"\""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class WaitlistCreate(BaseModel):
    """Incoming payload for a waitlist signup."""

    email: EmailStr = Field(..., description="Primary contact email")
    name: Optional[str] = Field(None, description="Full name")
    company: Optional[str] = Field(None, description="Company or organization")
    role: Optional[str] = Field(None, description="Role or title")
    source: Optional[str] = Field(
        default="landing", description="Attribution source for analytics"
    )


class WaitlistResponse(BaseModel):
    """Returned waitlist entry."""

    id: UUID
    email: EmailStr
    name: Optional[str]
    company: Optional[str]
    role: Optional[str]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True

