"""Schemas for anomaly detection."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class AnomalyResponse(BaseModel):
    anomalies: List[Dict]
    breach_probability: float
    projected_monthly_spend: float
    budget_usd_monthly: Optional[float]
    breach_probability_explain: "MetricValue | None" = None


from app.schemas.explainability import MetricValue

# Update forward references
AnomalyResponse.model_rebuild()
