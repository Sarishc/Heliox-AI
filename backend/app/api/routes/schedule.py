"""Scheduling forecast endpoint."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.services.scheduling_forecast import SchedulingForecastService

router = APIRouter()


@router.get(
    "/forecast",
    summary="Predictive capacity & scheduling forecast",
    description="Forecast GPU demand and congestion risk for scheduling.",
)
def get_schedule_forecast(
    horizon_days: int = Query(7, ge=1, le=30),
    provider: Optional[str] = Query(None),
    gpu_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    service = SchedulingForecastService(db)
    result = service.forecast(team_id=team_id, horizon_days=horizon_days, provider=provider, gpu_type=gpu_type)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    record_api_usage(db, team_id=team_id, endpoint="schedule_forecast")
    return result
