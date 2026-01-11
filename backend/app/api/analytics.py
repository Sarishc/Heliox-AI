"""
Analytics API endpoints for cost and usage insights.
"""
from datetime import date, datetime
from typing import List

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.team import Team

router = APIRouter()


class CostByModelResponse(BaseModel):
    """Response schema for cost aggregated by model."""
    model_name: str
    total_cost_usd: float = Field(description="Total cost in USD")
    job_count: int = Field(description="Number of jobs for this model")
    start_date: date
    end_date: date


class CostByTeamResponse(BaseModel):
    """Response schema for cost aggregated by team."""
    team_name: str
    team_id: str
    total_cost_usd: float = Field(description="Total cost in USD")
    job_count: int = Field(description="Number of jobs for this team")
    start_date: date
    end_date: date


@router.get(
    "/cost/by-model",
    response_model=List[CostByModelResponse],
    summary="Get cost aggregated by model"
)
def get_cost_by_model(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    # Public endpoint for demo - no authentication required
) -> Any:
    """
    Get total cost aggregated by ML model for a date range.
    
    This endpoint:
    1. Finds all jobs in the date range
    2. Groups by model_name
    3. Calculates total cost from CostSnapshot table
    4. Returns summarized data per model
    
    Query Parameters:
    - start: Start date (inclusive)
    - end: End date (inclusive)
    
    Note: Cost calculation is based on daily CostSnapshot data.
    The calculation sums costs for GPU types used by each model's jobs
    within the specified date range.
    """
    # Fetch cost by model for date range
    
    # Validate date range
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date"
        )
    
    # Query jobs grouped by model
    stmt = (
        select(
            Job.model_name,
            func.count(Job.id).label("job_count")
        )
        .where(
            func.date(Job.start_time) >= start,
            func.date(Job.start_time) <= end
        )
        .group_by(Job.model_name)
    )
    
    result = db.execute(stmt)
    jobs_by_model = result.all()
    
    if not jobs_by_model:
        return []
    
    # For each model, calculate total cost from CostSnapshot
    # This is a simplified approach that sums all costs in the date range
    # In production, you'd want to correlate job GPU usage with actual costs
    
    cost_by_model = []
    
    for model_name, job_count in jobs_by_model:
        # Get GPU types used by this model
        gpu_stmt = (
            select(Job.gpu_type, Job.provider)
            .where(
                Job.model_name == model_name,
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end
            )
            .distinct()
        )
        gpu_result = db.execute(gpu_stmt)
        gpu_info = gpu_result.all()
        
        # Calculate total cost for this model's GPU types
        total_cost = 0.0
        
        for gpu_type, provider in gpu_info:
            cost_stmt = (
                select(func.sum(CostSnapshot.cost_usd))
                .where(
                    CostSnapshot.date >= start,
                    CostSnapshot.date <= end,
                    CostSnapshot.gpu_type == gpu_type.lower(),
                    CostSnapshot.provider == provider.lower()
                )
            )
            cost_result = db.execute(cost_stmt)
            gpu_cost = cost_result.scalar_one_or_none() or 0.0
            total_cost += float(gpu_cost)
        
        cost_by_model.append(
            CostByModelResponse(
                model_name=model_name,
                total_cost_usd=round(total_cost, 2),
                job_count=job_count,
                start_date=start,
                end_date=end
            )
        )
    
    # Sort by total cost descending
    cost_by_model.sort(key=lambda x: x.total_cost_usd, reverse=True)
    
    return cost_by_model


@router.get(
    "/cost/by-team",
    response_model=List[CostByTeamResponse],
    summary="Get cost aggregated by team"
)
def get_cost_by_team(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    # Public endpoint for demo - no authentication required
) -> Any:
    """
    Get total cost aggregated by team for a date range.
    
    This endpoint:
    1. Finds all jobs in the date range
    2. Groups by team
    3. Calculates total cost from CostSnapshot table
    4. Returns summarized data per team
    
    Query Parameters:
    - start: Start date (inclusive)
    - end: End date (inclusive)
    
    Note: Cost calculation is based on daily CostSnapshot data.
    The calculation sums costs for GPU types used by each team's jobs
    within the specified date range.
    """
    # Fetch cost by team for date range
    
    # Validate date range
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date"
        )
    
    # Query jobs grouped by team
    stmt = (
        select(
            Team.id,
            Team.name,
            func.count(Job.id).label("job_count")
        )
        .join(Job, Job.team_id == Team.id)
        .where(
            func.date(Job.start_time) >= start,
            func.date(Job.start_time) <= end
        )
        .group_by(Team.id, Team.name)
    )
    
    result = db.execute(stmt)
    teams_data = result.all()
    
    if not teams_data:
        return []
    
    # For each team, calculate total cost from CostSnapshot
    cost_by_team = []
    
    for team_id, team_name, job_count in teams_data:
        # Get GPU types used by this team
        gpu_stmt = (
            select(Job.gpu_type, Job.provider)
            .where(
                Job.team_id == team_id,
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end
            )
            .distinct()
        )
        gpu_result = db.execute(gpu_stmt)
        gpu_info = gpu_result.all()
        
        # Calculate total cost for this team's GPU types
        total_cost = 0.0
        
        for gpu_type, provider in gpu_info:
            cost_stmt = (
                select(func.sum(CostSnapshot.cost_usd))
                .where(
                    CostSnapshot.date >= start,
                    CostSnapshot.date <= end,
                    CostSnapshot.gpu_type == gpu_type.lower(),
                    CostSnapshot.provider == provider.lower()
                )
            )
            cost_result = db.execute(cost_stmt)
            gpu_cost = cost_result.scalar_one_or_none() or 0.0
            total_cost += float(gpu_cost)
        
        cost_by_team.append(
            CostByTeamResponse(
                team_name=team_name,
                team_id=str(team_id),
                total_cost_usd=round(total_cost, 2),
                job_count=job_count,
                start_date=start,
                end_date=end
            )
        )
    
    # Sort by total cost descending
    cost_by_team.sort(key=lambda x: x.total_cost_usd, reverse=True)
    
    return cost_by_team

