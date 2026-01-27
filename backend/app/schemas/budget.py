"""Budget policy schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.budget import BudgetEnvironment


class BudgetPolicyBase(BaseModel):
    environment: BudgetEnvironment
    project: Optional[str] = Field(default=None, max_length=120)
    monthly_budget_usd: Decimal = Field(..., gt=0)
    alert_thresholds: list[float] = Field(default_factory=lambda: [0.7, 0.85, 1.0])
    is_enabled: bool = True


class BudgetPolicyCreate(BudgetPolicyBase):
    pass


class BudgetPolicyUpdate(BaseModel):
    environment: Optional[BudgetEnvironment] = None
    project: Optional[str] = Field(default=None, max_length=120)
    monthly_budget_usd: Optional[Decimal] = Field(default=None, gt=0)
    alert_thresholds: Optional[list[float]] = None
    is_enabled: Optional[bool] = None


class BudgetPolicyResponse(BudgetPolicyBase):
    id: UUID
    team_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BudgetStatus(BaseModel):
    policy: BudgetPolicyResponse
    month_start: date
    month_end: date
    mtd_spend_usd: Decimal
    budget_usd: Decimal
    percent_used: float
    forecasted_eom_spend_usd: Decimal
    predicted_breach_date: Optional[date]
    explain: "MetricValue | None" = None


class BudgetEventResponse(BaseModel):
    id: UUID
    team_id: UUID
    budget_policy_id: UUID
    date: date
    threshold: Decimal
    spend_usd: Decimal
    budget_usd: Decimal
    predicted_breach_date: Optional[date]
    delivered_via: str
    created_at: datetime

    class Config:
        from_attributes = True


from app.schemas.explainability import MetricValue

# Update forward references
BudgetStatus.model_rebuild()
