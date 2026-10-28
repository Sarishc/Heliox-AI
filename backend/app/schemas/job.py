"""Job schemas for request/response validation."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from pydantic_core import PydanticCustomError

JOB_STATUSES = ("pending", "running", "completed", "failed", "cancelled")

# External job identifier: what a client's scheduler calls the job (jobs.job_id, VARCHAR(100), unique)
JOB_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$"


def _as_utc(value: datetime) -> datetime:
    # Naive timestamps are treated as UTC, matching how the API stores them
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def check_chronology(start: Optional[datetime], end: Optional[datetime]) -> None:
    if start is not None and end is not None and _as_utc(end) < _as_utc(start):
        # PydanticCustomError (a ValueError) keeps the 422 body JSON-serializable
        raise PydanticCustomError("job_chronology", "end_time must not be before start_time")


class JobBase(BaseModel):
    """Base job schema with common fields."""

    model_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the ML model being executed",
    )

    gpu_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of GPU used (e.g., A100, H100, V100)",
    )

    provider: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cloud provider or platform (e.g., AWS, GCP, Azure)",
    )

    job_type: Optional[str] = Field(None, max_length=100, description="Job type (e.g., training, inference)")

    environment: Optional[str] = Field(None, max_length=100, description="Environment (e.g., prod, staging, dev)")

    project: Optional[str] = Field(None, max_length=120, description="Project or cost center identifier")

    status: str = Field(default="pending", max_length=50, description="Current status of the job")

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
    job_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=JOB_ID_PATTERN,
        description="External job ID from your scheduler; generated when omitted. Must be unique within the team.",
    )
    start_time: Optional[datetime] = Field(None, description="When the job started")
    end_time: Optional[datetime] = Field(None, description="When the job finished (for already-completed jobs)")

    @model_validator(mode="after")
    def _end_after_start(self) -> "JobCreate":
        check_chronology(self.start_time, self.end_time)
        return self


class JobUpdate(BaseModel):
    """Schema for updating a job. OWASP: extra='forbid' prevents mass assignment."""

    model_config = ConfigDict(extra="forbid")

    model_name: Optional[str] = Field(None, min_length=1, max_length=255)
    gpu_type: Optional[str] = Field(None, min_length=1, max_length=100)
    provider: Optional[str] = Field(None, min_length=1, max_length=100)
    project: Optional[str] = Field(None, max_length=120)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[str] = Field(None, max_length=50)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate job status if provided."""
        if v is None:
            return v
        if v not in JOB_STATUSES:
            raise ValueError(f"Status must be one of {list(JOB_STATUSES)}")
        return v

    @model_validator(mode="after")
    def _end_after_start(self) -> "JobUpdate":
        # Only checks a pair sent together; the route checks against stored values too
        check_chronology(self.start_time, self.end_time)
        return self


class Job(JobBase):
    """Schema for job responses."""

    id: UUID
    team_id: UUID
    job_id: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
