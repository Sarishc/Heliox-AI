"""Schemas for alert settings."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


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
        description="Enable email notifications"
    )
    email_recipients: Optional[str] = Field(
        default=None,
        description="Comma-separated list of email addresses"
    )
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack webhook URL (stored securely, masked in responses)"
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
    
    team_id: UUID = Field(..., description="Team ID")


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
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack webhook URL"
    )

    @field_validator("email_recipients")
    @classmethod
    def validate_email_recipients(cls, v: Optional[str]) -> Optional[str]:
        """Validate email recipients format (reuse AlertSettingsBase logic)."""
        if v is None or not v.strip():
            return v
        emails = [e.strip() for e in v.split(",")]
        for email in emails:
            if email and "@" not in email:
                raise ValueError(f"Invalid email format: {email}")
        return v


class AlertSettingsResponse(AlertSettingsBase):
    """Schema for alert settings response."""
    
    id: str
    team_id: UUID
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
                "slack_webhook_url": "***abcd1234",
                "created_at": "2026-01-09T12:00:00Z",
                "updated_at": "2026-01-09T12:00:00Z"
            }
        }


class SlackWebhookRequest(BaseModel):
    team_id: UUID
    slack_webhook_url: str


class SlackWebhookResponse(BaseModel):
    team_id: UUID
    configured: bool
    masked_webhook_url: Optional[str]


class EmailAlertsRequest(BaseModel):
    team_id: UUID
    enable_email: bool = True
    email_recipients: Optional[str] = Field(
        default=None,
        description="Comma-separated email addresses (required when enable_email=True)",
        examples=["alerts@example.com,finance@example.com"],
    )

    @field_validator("email_recipients")
    @classmethod
    def validate_email_recipients(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        emails = [e.strip() for e in v.split(",")]
        for email in emails:
            if not email:
                continue
            if "@" not in email:
                raise ValueError(f"Invalid email format: {email}")
        return v

    @model_validator(mode="after")
    def check_enable_email_recipients(self) -> "EmailAlertsRequest":
        if self.enable_email and (not self.email_recipients or not self.email_recipients.strip()):
            raise ValueError("At least one email address is required when enabling email alerts")
        return self


def _mask_email_recipients(recipients_str: Optional[str]) -> tuple[int, Optional[str]]:
    """Return (count, masked_display) for recipients."""
    if not recipients_str or not recipients_str.strip():
        return 0, None
    emails = [e.strip().lower() for e in recipients_str.split(",") if e.strip() and "@" in e]
    if not emails:
        return 0, None
    # Mask: show first char + *** + @domain
    masked = []
    for e in emails:
        parts = e.split("@", 1)
        if len(parts) == 2:
            masked.append(f"{parts[0][0]}***@{parts[1]}" if len(parts[0]) > 1 else f"***@{parts[1]}")
        else:
            masked.append("***")
    return len(emails), ", ".join(masked)


class EmailAlertsResponse(BaseModel):
    team_id: UUID
    enabled: bool
    recipient_count: int
    masked_recipients: Optional[str] = Field(
        default=None,
        description="Masked display of recipients (e.g. a***@example.com, b***@example.com)",
    )


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

