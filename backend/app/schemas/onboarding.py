"""Schemas for onboarding flow."""

from pydantic import BaseModel, Field


class OnboardingStatusResponse(BaseModel):
    """Checklist state derived from existing product data (no new tables)."""

    has_team: bool = False
    has_api_key: bool = False
    has_integration: bool = False
    has_slack_webhook: bool = False
    can_manage: bool = False
    role: str = "unknown"


class OnboardingRequest(BaseModel):
    team_name: str = Field(..., min_length=1, max_length=255)
    api_key_name: str = Field(default="Default key")
    monthly_budget_usd: float | None = Field(None, gt=0, description="Monthly infra budget in USD")


class OnboardingResponse(BaseModel):
    team_id: str
    api_key: str
    message: str
