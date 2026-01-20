"""Ingestion endpoints for GPU usage and costs."""
import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.schemas.ingest import UsageIngestRequest, CostIngestRequest, UsageMetric
from app.services.usage_ingestion import UsageIngestionService
from app.services.cost_ingestion import CostIngestionService, CostDataRecord
from app.plugins.registry import get_plugin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/usage",
    status_code=status.HTTP_200_OK,
    summary="Ingest GPU usage metrics",
    description="Ingest GPU usage samples and aggregate into daily snapshots."
)
def ingest_usage(
    payload: UsageIngestRequest | None = None,
    plugin: str | None = Query(None, description="Plugin name to fetch usage"),
    start_date: date | None = Query(None, description="Start date for plugin fetch"),
    end_date: date | None = Query(None, description="End date for plugin fetch"),
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id = get_effective_team_id(api_key)
    if plugin:
        if not start_date or not end_date or end_date < start_date:
            raise HTTPException(status_code=400, detail="start_date/end_date required for plugin ingest")
        plugin_cls = get_plugin(plugin)
        if not plugin_cls:
            raise HTTPException(status_code=404, detail="Plugin not found")
        plugin_instance = plugin_cls()
        health_error = plugin_instance.healthcheck()
        if health_error:
            raise HTTPException(status_code=503, detail=health_error)
        metrics = [
            UsageMetric(
                timestamp=datetime.combine(record.date, datetime.min.time()),
                provider=record.provider,
                gpu_type=record.gpu_type,
                gpu_hours=record.gpu_hours,
                tags={"source": plugin},
            )
            for record in plugin_instance.fetch_usage(start_date=start_date, end_date=end_date)
        ]
        payload = UsageIngestRequest(metrics=metrics)
    if payload is None:
        raise HTTPException(status_code=400, detail="Payload required for ingestion")
    service = UsageIngestionService(db)
    result = service.ingest_usage_metrics(team_id=team_id, metrics=payload.metrics)
    record_api_usage(db, team_id=team_id, endpoint="ingest_usage")
    return {"status": "success", "result": result}


@router.post(
    "/cost",
    status_code=status.HTTP_200_OK,
    summary="Ingest GPU cost data",
    description="Ingest GPU cost records (team scoped)."
)
def ingest_cost(
    payload: CostIngestRequest | None = None,
    plugin: str | None = Query(None, description="Plugin name to fetch costs"),
    start_date: date | None = Query(None, description="Start date for plugin fetch"),
    end_date: date | None = Query(None, description="End date for plugin fetch"),
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id = get_effective_team_id(api_key)
    service = CostIngestionService(db)
    if plugin:
        if not start_date or not end_date or end_date < start_date:
            raise HTTPException(status_code=400, detail="start_date/end_date required for plugin ingest")
        plugin_cls = get_plugin(plugin)
        if not plugin_cls:
            raise HTTPException(status_code=404, detail="Plugin not found")
        plugin_instance = plugin_cls()
        health_error = plugin_instance.healthcheck()
        if health_error:
            raise HTTPException(status_code=503, detail=health_error)
        records = [
            CostDataRecord(
                team_id=str(team_id),
                date=record.date,
                provider=record.provider,
                gpu_type=record.gpu_type,
                cost_usd=record.cost_usd,
            )
            for record in plugin_instance.fetch_cost(start_date=start_date, end_date=end_date)
        ]
        result = service.ingest_cost_records(records=records, team_id=str(team_id))
        record_api_usage(db, team_id=team_id, endpoint="ingest_cost_plugin")
        return {"status": "success", "result": result}
    if payload is None:
        raise HTTPException(status_code=400, detail="Payload required for ingestion")
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
