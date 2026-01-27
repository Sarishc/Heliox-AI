"""Schemas for business KPI metrics."""
from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict
from app.schemas.explainability import MetricValue


class BusinessMetricCreate(BaseModel):
    date: date
    revenue_usd: float = Field(..., ge=0)
    active_users: int = Field(..., ge=0)
    requests: int = Field(..., ge=0)


class BusinessMetricIngestRequest(BaseModel):
    metrics: List[BusinessMetricCreate]


class BusinessMetricResponse(BusinessMetricCreate):
    id: UUID
    team_id: UUID
    
    model_config = ConfigDict(from_attributes=True)


class BusinessEfficiencyTrend(BaseModel):
    date: date
    revenue_per_gpu_dollar: float
    cost_per_active_user: float
    requests_per_gpu_dollar: float
    revenue_per_gpu_dollar_smoothed: float
    cost_per_active_user_smoothed: float
    requests_per_gpu_dollar_smoothed: float


class BusinessEfficiencyResponse(BaseModel):
    start_date: date
    end_date: date
    revenue_per_gpu_dollar: float
    cost_per_active_user: float
    efficiency_trends: List[BusinessEfficiencyTrend]
    revenue_per_gpu_dollar_explain: Optional[MetricValue] = None
    cost_per_active_user_explain: Optional[MetricValue] = None
