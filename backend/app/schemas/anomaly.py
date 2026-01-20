"""Schemas for anomaly detection."""
from typing import Dict, List, Optional

from pydantic import BaseModel


class AnomalyResponse(BaseModel):
    anomalies: List[Dict]
    breach_probability: float
    projected_monthly_spend: float
    budget_usd_monthly: Optional[float]
