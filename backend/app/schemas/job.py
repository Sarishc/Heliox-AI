"""Job schemas for request/response validation."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


class JobBase(BaseModel):
    """Base job schema with common fields."""
    
    model_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the ML model being executed"
    )
    
    gpu_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of GPU used (e.g., A100, H100, V100)"
    )
    
    provider: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cloud provider or platform (e.g., AWS, GCP, Azure)"
    )
    
    status: str = Field(
        default="pending",
        max_length=50,
        description="Current status of the job"
    )
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate job status is one of the allowed values."""
        allowed_statuses = ["pending", "running", "completed", "failed", "cancelled"]
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of {allowed_statuses}")
        return v


class JobCreate(JobBase):
    """Schema for creating a new job."""
    
    team_id: UUID = Field(..., description="ID of the team that owns this job")
    start_time: Optional[datetime] = Field(None, description="When the job started")


class JobUpdate(BaseModel):
    """Schema for updating a job."""
    
    model_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gpu_type: Optional[str] = Field(None, min_length=1, max_length=100)
    provider: Optional[str] = Field(None, min_length=1, max_length=100)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = Field(None, max_length=50)
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate job status if provided."""
        if v is None:
            return v
        allowed_statuses = ["pending", "running", "completed", "failed", "cancelled"]
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of {allowed_statuses}")
        return v


class Job(JobBase):
    """Schema for job responses."""
    
    id: UUID
    team_id: UUID
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

