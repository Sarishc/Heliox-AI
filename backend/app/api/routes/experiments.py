"""Experiment endpoints."""
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.experiment import Experiment, ExperimentResult
from app.models.team_api_key import TeamAPIKey
from app.schemas.experiment import ExperimentCreate, ExperimentResponse, ExperimentResultResponse
from app.services.experiments import ExperimentService

router = APIRouter()


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    team_id = get_effective_team_id(team_api_key)
    service = ExperimentService(db)
    experiment = service.create_experiment(
        team_id=team_id,
        name=payload.name,
        baseline_policy=payload.baseline_policy,
        optimized_policy=payload.optimized_policy,
        start_date=payload.start_date,
        end_date=payload.end_date,
        assignment_ratio=payload.assignment_ratio,
    )
    record_api_usage(db, team_id=team_id, endpoint="experiments_create")
    return experiment


@router.get("/{experiment_id}/results", response_model=ExperimentResultResponse)
def get_experiment_results(
    experiment_id: UUID,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    experiment = (
        db.query(Experiment)
        .filter(Experiment.id == experiment_id, Experiment.team_id == team_id)
        .first()
    )
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    service = ExperimentService(db)
    result = service.compute_results(experiment=experiment)
    record_api_usage(db, team_id=team_id, endpoint="experiments_results")
    return ExperimentResultResponse(
        experiment_id=experiment.id,
        computed_at=result.computed_at,
        metrics=result.metrics,
    )
