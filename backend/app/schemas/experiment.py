"""Schemas for optimization experiments."""
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    baseline_policy: str = Field(..., min_length=1, max_length=255)
    optimized_policy: str = Field(..., min_length=1, max_length=255)
    start_date: date
    end_date: date
    assignment_ratio: float = Field(0.5, gt=0, lt=1)


class ExperimentResponse(BaseModel):
    id: UUID
    team_id: UUID
    name: str
    baseline_policy: str
    optimized_policy: str
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ExperimentResultResponse(BaseModel):
    experiment_id: UUID
    computed_at: datetime
    metrics: Dict
