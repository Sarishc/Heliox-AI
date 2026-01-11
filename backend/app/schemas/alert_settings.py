"""Schemas for alert settings."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AlertSettingsBase(BaseModel):
    """Base schema for alert settings."""
    
    burn_rate_threshold_usd_per_day: Decimal = Field(
        default=Decimal("10000.00"),
        ge=0,
        description="Daily spend threshold for burn rate alerts (USD)"
    )
    enable_slack: bool = Field(
        default=True,
        description="Enable Slack notifications"
    )
    enable_email: bool = Field(
        default=False,
        description="Enable email notifications (future feature)"
    )
    email_recipients: Optional[str] = Field(
        default=None,
        description="Comma-separated list of email addresses"
    )
    
    @field_validator("email_recipients")
    @classmethod
    def validate_email_recipients(cls, v: Optional[str]) -> Optional[str]:
        """Validate email recipients format."""
        if v is None:
            return v
        
        # Basic validation - check for @ symbols
        emails = [email.strip() for email in v.split(",")]
        for email in emails:
            if email and "@" not in email:
                raise ValueError(f"Invalid email format: {email}")
        
        return v


class AlertSettingsCreate(AlertSettingsBase):
    """Schema for creating alert settings."""
    
    team_id: str = Field(..., description="Team ID")


class AlertSettingsUpdate(BaseModel):
    """Schema for updating alert settings."""
    
    burn_rate_threshold_usd_per_day: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Daily spend threshold for burn rate alerts (USD)"
    )
    enable_slack: Optional[bool] = Field(
        default=None,
        description="Enable Slack notifications"
    )
    enable_email: Optional[bool] = Field(
        default=None,
        description="Enable email notifications"
    )
    email_recipients: Optional[str] = Field(
        default=None,
        description="Comma-separated list of email addresses"
    )


class AlertSettingsResponse(AlertSettingsBase):
    """Schema for alert settings response."""
    
    id: str
    team_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "team_id": "team-123",
                "burn_rate_threshold_usd_per_day": 10000.00,
                "enable_slack": True,
                "enable_email": False,
                "email_recipients": "team-lead@example.com,finance@example.com",
                "created_at": "2026-01-09T12:00:00Z",
                "updated_at": "2026-01-09T12:00:00Z"
            }
        }


class DailyDigestTeamData(BaseModel):
    """Schema for team-specific daily digest data."""
    
    team_id: str
    team_name: str
    daily_cost: float
    weekly_cost: float
    monthly_cost: float
    daily_change_percent: float
    top_models: list[dict]
    top_recommendations: list[dict]
    total_potential_savings: float


class DailyDigestPayload(BaseModel):
    """Schema for daily digest payload."""
    
    date: str
    total_daily_cost: float
    total_weekly_cost: float
    total_monthly_cost: float
    teams: list[DailyDigestTeamData]
    global_top_models: list[dict]
    global_recommendations: list[dict]
    global_potential_savings: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2026-01-09",
                "total_daily_cost": 25000.00,
                "total_weekly_cost": 175000.00,
                "total_monthly_cost": 750000.00,
                "teams": [
                    {
                        "team_id": "team-123",
                        "team_name": "ML Research",
                        "daily_cost": 12000.00,
                        "weekly_cost": 84000.00,
                        "monthly_cost": 360000.00,
                        "daily_change_percent": 5.2,
                        "top_models": [
                            {"model_name": "GPT-4", "cost": 5000.00}
                        ],
                        "top_recommendations": [
                            {
                                "title": "Idle GPU: H100",
                                "savings": 1000.00,
                                "severity": "high"
                            }
                        ],
                        "total_potential_savings": 1000.00
                    }
                ],
                "global_top_models": [
                    {"model_name": "Stable Diffusion XL", "cost": 10000.00}
                ],
                "global_recommendations": [
                    {
                        "title": "Idle GPU: A100",
                        "savings": 2000.00,
                        "severity": "high"
                    }
                ],
                "global_potential_savings": 5000.00
            }
        }

