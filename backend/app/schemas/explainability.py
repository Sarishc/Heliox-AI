"""Schemas for metric explainability and confidence."""
from typing import List, Optional

from pydantic import BaseModel, Field


class Component(BaseModel):
    name: str
    value: float | int | str
    unit: Optional[str] = None
    source: Optional[str] = None


class Explanation(BaseModel):
    formula: str
    components: List[Component]
    assumptions: List[str]


class MetricValue(BaseModel):
    value: float | int
    unit: str
    window: str
    confidence: float = Field(..., ge=0, le=1)
    confidence_reasons: List[str]
    explanation: Explanation
