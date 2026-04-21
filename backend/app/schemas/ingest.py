"""Schemas for ingestion endpoints."""

from datetime import datetime, date as date_type
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class UsageMetric(BaseModel):
    timestamp: datetime = Field(..., description="Sample timestamp")
    provider: str = Field(..., min_length=1, max_length=100)
    gpu_type: str = Field(..., min_length=1, max_length=100)
    gpu_hours: Decimal = Field(..., ge=0, description="GPU hours for this interval")
    tags: Optional[dict] = Field(default_factory=dict)


class UsageIngestRequest(BaseModel):
    metrics: List[UsageMetric] = Field(..., min_length=1)


class CostMetric(BaseModel):
    date: date_type = Field(..., description="Date for cost snapshot")
    provider: str = Field(..., min_length=1, max_length=100)
    gpu_type: str = Field(..., min_length=1, max_length=100)
    cost_usd: Decimal = Field(..., gt=0)


class CostIngestRequest(BaseModel):
    records: List[CostMetric] = Field(..., min_length=1)
