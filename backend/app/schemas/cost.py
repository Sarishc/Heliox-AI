"""Cost and usage snapshot schemas for request/response validation."""
from datetime import date as date_type, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class CostSnapshotBase(BaseModel):
    """Base cost snapshot schema with common fields."""
    
    date: date_type = Field(..., description="Date of the cost snapshot")
    
    provider: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cloud provider or platform"
    )
    
    gpu_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of GPU"
    )
    
    cost_usd: Decimal = Field(
        ...,
        gt=0,
        description="Cost in USD"
    )


class CostSnapshotCreate(CostSnapshotBase):
    """Schema for creating a new cost snapshot."""
    pass


class CostSnapshot(CostSnapshotBase):
    """Schema for cost snapshot responses."""
    
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class UsageSnapshotBase(BaseModel):
    """Base usage snapshot schema with common fields."""
    
    date: date_type = Field(..., description="Date of the usage snapshot")
    
    provider: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cloud provider or platform"
    )
    
    gpu_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of GPU"
    )
    
    gpu_hours: Decimal = Field(
        ...,
        ge=0,
        description="Number of GPU hours used"
    )


class UsageSnapshotCreate(UsageSnapshotBase):
    """Schema for creating a new usage snapshot."""
    pass


class UsageSnapshot(UsageSnapshotBase):
    """Schema for usage snapshot responses."""
    
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

