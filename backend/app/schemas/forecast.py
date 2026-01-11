"""Schemas for forecasting endpoints."""
from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ForecastPoint(BaseModel):
    """A single forecast point with confidence interval."""
    
    date: str = Field(..., description="Date of the forecast")
    value: float = Field(..., description="Forecasted value")
    lower_bound: float = Field(..., description="Lower confidence bound (95%)")
    upper_bound: float = Field(..., description="Upper confidence bound (95%)")


class HistoricalPoint(BaseModel):
    """A single historical data point."""
    
    date: str = Field(..., description="Date of the observation")
    value: float = Field(..., description="Observed value")


class ForecastMetadata(BaseModel):
    """Metadata about the forecast."""
    
    historical_data_points: int = Field(..., description="Number of historical data points used")
    forecast_generated_at: str = Field(..., description="Date when forecast was generated")


class ForecastResponse(BaseModel):
    """Response schema for forecast endpoints."""
    
    provider: Optional[str] = Field(None, description="Provider filter applied")
    gpu_type: Optional[str] = Field(None, description="GPU type filter applied")
    horizon_days: int = Field(..., description="Number of days forecasted")
    forecast_method: str = Field(..., description="Method used for forecasting (moving_average or lightgbm)")
    historical: List[HistoricalPoint] = Field(..., description="Historical data points")
    forecast: List[ForecastPoint] = Field(..., description="Forecasted data points")
    metadata: ForecastMetadata = Field(..., description="Forecast metadata")
    error: Optional[str] = Field(None, description="Error message if forecast failed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "provider": "aws",
                "gpu_type": "h100",
                "horizon_days": 7,
                "forecast_method": "moving_average",
                "historical": [
                    {"date": "2026-01-01", "value": 120.5},
                    {"date": "2026-01-02", "value": 125.3}
                ],
                "forecast": [
                    {
                        "date": "2026-01-15",
                        "value": 130.0,
                        "lower_bound": 110.0,
                        "upper_bound": 150.0
                    }
                ],
                "metadata": {
                    "historical_data_points": 14,
                    "forecast_generated_at": "2026-01-14"
                }
            }
        }

