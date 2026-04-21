"""Pydantic schemas for integrations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IntegrationConnectionCreate(BaseModel):
    """Schema for creating an integration connection."""

    provider: str = Field(..., description="Integration provider (aws, gcp, stripe, etc.)")
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="User-friendly name for this integration",
    )
    description: Optional[str] = Field(None, description="Optional description")
    config: Dict[str, Any] = Field(..., description="Integration configuration (will be encrypted)")
    auto_sync_enabled: bool = Field(True, description="Enable automatic syncing")
    sync_interval_minutes: int = Field(60, ge=5, le=1440, description="Sync interval in minutes (5-1440)")


class IntegrationConnectionResponse(BaseModel):
    """Schema for integration connection response."""

    id: UUID
    team_id: UUID
    provider: str
    name: str
    description: Optional[str]
    config: Dict[str, Any]  # Masked sensitive fields
    status: str
    last_error: Optional[str]
    last_sync_at: Optional[datetime]
    last_successful_sync_at: Optional[datetime]
    auto_sync_enabled: bool
    sync_interval_minutes: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntegrationListResponse(BaseModel):
    """Schema for listing integrations."""

    connections: List[IntegrationConnectionResponse]
    total: int


class IntegrationSyncRunResponse(BaseModel):
    """Schema for sync run response."""

    id: UUID
    connection_id: UUID
    started_at: datetime
    finished_at: Optional[datetime]
    status: str
    error: Optional[str]
    metrics: Optional[Dict[str, Any]]
    triggered_by: str

    model_config = {"from_attributes": True}


class IntegrationHealthResponse(BaseModel):
    """Schema for health check response."""

    connection_id: UUID
    status: str  # healthy, degraded, unhealthy
    message: str
    details: Dict[str, Any]


class AvailableIntegrationResponse(BaseModel):
    """Schema for available integration metadata."""

    provider: str
    display_name: str
    description: str
    enabled: bool
    config_schema: Optional[Dict[str, Any]]
