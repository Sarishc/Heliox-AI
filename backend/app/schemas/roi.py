"""Schemas for ROI / savings dashboard."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class SavingsByCategory(BaseModel):
    """Savings breakdown by recommendation category."""
    type: str = Field(..., description="Recommendation type (idle_gpu, long_running_job, off_hours_usage)")
    label: str = Field(..., description="Human-readable label")
    estimated_savings_usd: float = Field(0.0, ge=0, description="Estimated savings in USD (potential)")
    count: int = Field(0, ge=0, description="Number of opportunities in this category")


class TopRecommendation(BaseModel):
    """Single top savings opportunity."""
    title: str
    type: str
    estimated_savings_usd: float = Field(..., ge=0)
    severity: str = "medium"


class ProviderBreakdown(BaseModel):
    """Cost breakdown by cloud provider."""
    provider: str
    cost_usd: float = Field(..., ge=0)
    share_percent: float = Field(0.0, ge=0, le=100)


class ROIDashboardResponse(BaseModel):
    """
    ROI / savings dashboard payload.

    All savings figures are estimated/potential based on identified opportunities.
    Realized savings tracking is not yet implemented.
    """
    start_date: date
    end_date: date
    total_spend_usd: float = Field(..., ge=0, description="Total GPU spend in period")
    estimated_potential_savings_usd: float = Field(
        0.0, ge=0,
        description="Estimated potential savings from all recommendations (not yet realized)"
    )
    savings_percent_of_spend: float = Field(
        0.0, ge=0, le=100,
        description="Potential savings as % of total spend (0 if no spend)"
    )
    savings_by_category: List[SavingsByCategory] = Field(
        default_factory=list,
        description="Savings grouped by recommendation type"
    )
    top_recommendations: List[TopRecommendation] = Field(
        default_factory=list,
        description="Top 5 savings opportunities by estimated value"
    )
    provider_breakdown: List[ProviderBreakdown] = Field(
        default_factory=list,
        description="Cost by cloud provider"
    )
    anomaly_count: int = Field(0, ge=0, description="Number of spend/utilization anomalies detected")
    recommendation_count: int = Field(0, ge=0, description="Total number of recommendations")
    disclaimer: str = Field(
        default="All savings are estimated potential. Actual savings depend on implementation.",
        description="Honesty disclaimer for the dashboard"
    )
