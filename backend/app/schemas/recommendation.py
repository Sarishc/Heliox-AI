"""Recommendation schemas for Heliox-AI."""
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RecommendationSeverity(str, Enum):
    """Severity levels for recommendations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationType(str, Enum):
    """Types of recommendations."""
    IDLE_GPU = "idle_gpu"
    LONG_RUNNING_JOB = "long_running_job"
    OFF_HOURS_USAGE = "off_hours_usage"
    COST_OPTIMIZATION = "cost_optimization"


class RecommendationEvidence(BaseModel):
    """Structured evidence supporting a recommendation."""
    
    # Common fields
    date_range: Optional[Dict[str, str]] = Field(
        None, description="Date range for the evidence (start_date, end_date)"
    )
    
    # Job-specific evidence
    job_id: Optional[str] = Field(None, description="Related job ID")
    job_runtime_hours: Optional[float] = Field(None, description="Job runtime in hours")
    job_start_time: Optional[datetime] = Field(None, description="Job start time")
    job_end_time: Optional[datetime] = Field(None, description="Job end time")
    
    # Cost/usage evidence
    total_cost_usd: Optional[float] = Field(None, description="Total cost in USD")
    expected_usage_hours: Optional[float] = Field(None, description="Expected GPU hours")
    actual_usage_hours: Optional[float] = Field(None, description="Actual GPU hours")
    waste_percentage: Optional[float] = Field(None, description="Percentage of wasted resources")
    
    # GPU/provider evidence
    gpu_type: Optional[str] = Field(None, description="GPU type")
    provider: Optional[str] = Field(None, description="Cloud provider")
    team_name: Optional[str] = Field(None, description="Team name")
    model_name: Optional[str] = Field(None, description="ML model name")
    
    # Additional context
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )


class Recommendation(BaseModel):
    """A single recommendation for cost optimization or improvement."""
    
    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for the recommendation"
    )
    
    type: RecommendationType = Field(
        ..., description="Type of recommendation"
    )
    
    title: str = Field(
        ..., min_length=1, max_length=200, description="Short title of the recommendation"
    )
    
    description: str = Field(
        ..., min_length=1, max_length=1000, description="Detailed description"
    )
    
    severity: RecommendationSeverity = Field(
        ..., description="Severity level (low, medium, high)"
    )
    
    estimated_savings_usd: float = Field(
        0.0, ge=0, description="Estimated cost savings in USD if implemented"
    )
    
    evidence: RecommendationEvidence = Field(
        ..., description="Structured evidence supporting this recommendation"
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the recommendation was generated"
    )


class RecommendationFilters(BaseModel):
    """Filters for recommendation queries."""
    
    start_date: date = Field(..., description="Start date for analysis")
    end_date: date = Field(..., description="End date for analysis")
    
    min_severity: Optional[RecommendationSeverity] = Field(
        None, description="Minimum severity to include"
    )
    
    types: Optional[List[RecommendationType]] = Field(
        None, description="Filter by recommendation types"
    )
    
    team_id: Optional[UUID] = Field(
        None, description="Filter by team ID"
    )
    
    min_savings: Optional[float] = Field(
        None, ge=0, description="Minimum estimated savings to include"
    )


class RecommendationResponse(BaseModel):
    """Response containing recommendations and summary."""
    
    recommendations: List[Recommendation] = Field(
        ..., description="List of recommendations"
    )
    
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics about recommendations"
    )
    
    date_range: Dict[str, str] = Field(
        ..., description="Date range used for analysis"
    )
    
    total_estimated_savings_usd: float = Field(
        0.0, description="Sum of all estimated savings"
    )

