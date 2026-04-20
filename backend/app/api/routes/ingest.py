"""Ingestion endpoints for GPU usage and costs."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.schemas.ingest import UsageIngestRequest, CostIngestRequest
from app.services.usage_ingestion import UsageIngestionService
from app.services.cost_ingestion import CostIngestionService, CostDataRecord

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/usage",
    status_code=status.HTTP_200_OK,
    summary="Ingest GPU usage metrics",
    description="Ingest GPU usage samples and aggregate into daily snapshots.",
)
def ingest_usage(
    payload: UsageIngestRequest,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id = get_effective_team_id(api_key)
    service = UsageIngestionService(db)
    result = service.ingest_usage_metrics(team_id=team_id, metrics=payload.metrics)
    record_api_usage(db, team_id=team_id, endpoint="ingest_usage")
    return {"status": "success", "result": result}


@router.post(
    "/cost",
    status_code=status.HTTP_200_OK,
    summary="Ingest GPU cost data",
    description="Ingest GPU cost records (team scoped).",
)
def ingest_cost(
    payload: CostIngestRequest,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id = get_effective_team_id(api_key)
    service = CostIngestionService(db)
    records = [
        CostDataRecord(
            team_id=str(team_id),
            date=record.date,
            provider=record.provider,
            gpu_type=record.gpu_type,
            cost_usd=record.cost_usd,
        )
        for record in payload.records
    ]
    result = service.ingest_cost_records(records=records, team_id=str(team_id))
    record_api_usage(db, team_id=team_id, endpoint="ingest_cost")
    return {"status": "success", "result": result}
