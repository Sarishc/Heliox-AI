"""Schemas for savings summary endpoint."""

from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field


class SavingsSummaryResponse(BaseModel):
    start_date: date
    end_date: date
    total_spend_usd: float = Field(..., ge=0)
    estimated_idle_waste_usd: float = Field(..., ge=0)
    recommended_savings_usd: float = Field(..., ge=0)
    total_spend_explain: "MetricValue | None" = None
    idle_waste_explain: "MetricValue | None" = None
    recommended_savings_explain: "MetricValue | None" = None


from app.schemas.explainability import MetricValue

# Update forward references
SavingsSummaryResponse.model_rebuild()
