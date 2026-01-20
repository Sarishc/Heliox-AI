"""Anomaly detection endpoint."""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.schemas.anomaly import AnomalyResponse
from app.services.anomaly import AnomalyDetectionService

router = APIRouter()


@router.get("", response_model=AnomalyResponse, summary="Detect spend/utilization anomalies")
def get_anomalies(
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    service = AnomalyDetectionService(db)
    result = service.detect(team_id=team_id)
    record_api_usage(db, team_id=team_id, endpoint="anomalies")
    return result.__dict__
