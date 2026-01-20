"""Schemas for savings summary endpoint."""
from datetime import date
from pydantic import BaseModel, Field


class SavingsSummaryResponse(BaseModel):
    start_date: date
    end_date: date
    total_spend_usd: float = Field(..., ge=0)
    estimated_idle_waste_usd: float = Field(..., ge=0)
    recommended_savings_usd: float = Field(..., ge=0)
