"""Schemas for saved reports and exports."""
from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReportSection(str, Enum):
    overview_kpis = "overview_kpis"
    daily_spend = "daily_spend"
    idle_waste = "idle_waste"
    top_models = "top_models"
    top_recommendations = "top_recommendations"


class ReportFilters(BaseModel):
    environment: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=255)
    team: Optional[str] = Field(default=None, max_length=255)


class ReportConfig(BaseModel):
    start_date: date
    end_date: date
    filters: ReportFilters = Field(default_factory=ReportFilters)
    sections: list[ReportSection] = Field(default_factory=list)


class SavedReportBase(BaseModel):
    name: str = Field(..., max_length=160)
    description: Optional[str] = Field(default=None, max_length=500)
    config: ReportConfig


class SavedReportCreate(SavedReportBase):
    pass


class SavedReportUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=500)
    config: Optional[ReportConfig] = None


class SavedReportResponse(SavedReportBase):
    id: UUID
    team_id: UUID
    created_by_user_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    config: ReportConfig = Field(alias="config_json")

    class Config:
        from_attributes = True
        populate_by_name = True


class ReportFileType(str, Enum):
    csv = "csv"
    pdf = "pdf"


class ReportRunCreate(BaseModel):
    file_type: ReportFileType = Field(..., description="Output format for the report run")


class ReportRunResponse(BaseModel):
    id: UUID
    team_id: UUID
    report_id: UUID
    status: str
    generated_at: Optional[datetime]
    storage_path: Optional[str]
    file_type: Optional[ReportFileType]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReportShareCreate(BaseModel):
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class ReportShareResponse(BaseModel):
    id: UUID
    report_id: UUID
    team_id: UUID
    expires_at: datetime
    created_at: datetime
    share_url: str

    class Config:
        from_attributes = True


class PublicReportResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    config: ReportConfig
    generated_at: Optional[datetime]
    data: dict
