"""
Analytics API endpoints for cost and usage insights.
"""

from datetime import date, timedelta
from typing import List, Union

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.auth.team_resolution import TeamContext, get_team_api_key_or_session_optional
from app.core.db import get_db
from app.core.usage_tracking import record_api_usage
from app.core.tenant import get_effective_team_id
from app.models.team_api_key import TeamAPIKey
from app.schemas.savings import SavingsSummaryResponse
from app.schemas.roi import ROIDashboardResponse
from app.schemas.explainability import Component, MetricValue
from app.services.explainability import explain_metric
from app.schemas.business_metric import (
    BusinessMetricIngestRequest,
    BusinessMetricResponse,
    BusinessEfficiencyResponse,
    BusinessEfficiencyTrend,
)
from app.schemas.recommendation import RecommendationFilters
from app.services.recommendations import RecommendationEngine
from app.services.roi_dashboard import get_roi_dashboard
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.business_metric import BusinessMetric
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
    runtime_share: float | None = None
    explain: MetricValue | None = None


class CostByTeamResponse(BaseModel):
    """Response schema for cost aggregated by team."""

    team_name: str
    team_id: str
    total_cost_usd: float = Field(description="Total cost in USD")
    job_count: int = Field(description="Number of jobs for this team")
    start_date: date
    end_date: date
    cost_share: float | None = None
    explain: MetricValue | None = None


class CostByModelEnvelope(BaseModel):
    items: List[CostByModelResponse]
    explain: MetricValue
    point_explain: dict[str, MetricValue] | None = None


class CostByTeamEnvelope(BaseModel):
    items: List[CostByTeamResponse]
    explain: MetricValue
    point_explain: dict[str, MetricValue] | None = None


@router.get(
    "/cost/by-model",
    response_model=Union[List[CostByModelResponse], CostByModelEnvelope],
    summary="Get cost aggregated by model",
)
def get_cost_by_model(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
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
    include_explain = include_explain is True

    # Fetch cost by model for date range

    # Validate date range
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )

    team_id = get_effective_team_id(team_api_key)

    # Aggregate job runtime per model per day
    dialect_name = db.bind.dialect.name if db.bind else ""
    daily_runtime = {}
    daily_job_count = {}
    model_runtime = {}
    model_job_count = {}
    model_job_count_by_day = {}

    if dialect_name == "sqlite":
        jobs = (
            db.query(Job)
            .filter(
                Job.team_id == team_id,
                Job.start_time.isnot(None),
                Job.end_time.isnot(None),
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end,
            )
            .all()
        )
        if not jobs:
            return []
        for job in jobs:
            day = job.start_time.date()
            runtime = (job.end_time - job.start_time).total_seconds()
            daily_runtime[day] = daily_runtime.get(day, 0.0) + runtime
            daily_job_count[day] = daily_job_count.get(day, 0) + 1
            model_runtime[(day, job.model_name)] = model_runtime.get((day, job.model_name), 0.0) + runtime
            model_job_count[job.model_name] = model_job_count.get(job.model_name, 0) + 1
            model_job_count_by_day[(day, job.model_name)] = model_job_count_by_day.get((day, job.model_name), 0) + 1
    else:
        runtime_expr = func.sum(func.extract("epoch", Job.end_time - Job.start_time))
        runtime_stmt = (
            select(
                func.date(Job.start_time).label("day"),
                Job.model_name,
                func.count(Job.id).label("job_count"),
                runtime_expr.label("runtime_seconds"),
            )
            .where(
                Job.team_id == team_id,
                Job.start_time.isnot(None),
                Job.end_time.isnot(None),
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end,
            )
            .group_by(func.date(Job.start_time), Job.model_name)
        )
        runtime_rows = db.execute(runtime_stmt).all()
        if not runtime_rows:
            return []
        for day, model_name, job_count, runtime_seconds in runtime_rows:
            runtime = float(runtime_seconds or 0.0)
            daily_runtime[day] = daily_runtime.get(day, 0.0) + runtime
            daily_job_count[day] = daily_job_count.get(day, 0) + int(job_count)
            model_runtime[(day, model_name)] = model_runtime.get((day, model_name), 0.0) + runtime
            model_job_count[model_name] = model_job_count.get(model_name, 0) + int(job_count)
            model_job_count_by_day[(day, model_name)] = model_job_count_by_day.get((day, model_name), 0) + int(
                job_count
            )

    daily_cost_rows = db.execute(
        select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd))
        .where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date >= start,
            CostSnapshot.date <= end,
        )
        .group_by(CostSnapshot.date)
    ).all()
    daily_costs = {row[0]: float(row[1] or 0.0) for row in daily_cost_rows}

    model_costs = {}
    model_total_runtime = {}
    for (day, model_name), runtime in model_runtime.items():
        daily_cost = daily_costs.get(day, 0.0)
        if daily_cost <= 0:
            continue
        total_runtime = daily_runtime.get(day, 0.0)
        if total_runtime > 0 and runtime > 0:
            share = runtime / total_runtime
        else:
            total_jobs = daily_job_count.get(day, 0)
            model_jobs = model_job_count_by_day.get((day, model_name), 0)
            share = (model_jobs / total_jobs) if total_jobs > 0 else 0.0
        model_costs[model_name] = model_costs.get(model_name, 0.0) + (daily_cost * share)
        model_total_runtime[model_name] = model_total_runtime.get(model_name, 0.0) + runtime

    total_runtime = sum(model_total_runtime.values()) if model_total_runtime else 0.0
    cost_by_model = [
        CostByModelResponse(
            model_name=model_name,
            total_cost_usd=round(model_costs.get(model_name, 0.0), 2),
            job_count=model_job_count.get(model_name, 0),
            start_date=start,
            end_date=end,
            runtime_share=(
                round(model_total_runtime.get(model_name, 0.0) / total_runtime, 4) if total_runtime > 0 else None
            ),
            explain=(
                explain_metric(
                    value=round(model_costs.get(model_name, 0.0), 2),
                    unit="USD",
                    window=f"{start.isoformat()} to {end.isoformat()}",
                    formula="sum(daily_cost * runtime_share)",
                    components=[
                        Component(
                            name="model_runtime_seconds",
                            value=round(model_total_runtime.get(model_name, 0.0), 2),
                            unit="seconds",
                            source="jobs",
                        ),
                        Component(
                            name="job_count",
                            value=model_job_count.get(model_name, 0),
                            unit="jobs",
                            source="jobs",
                        ),
                    ],
                    assumptions=["Runtime share falls back to job-count share when runtime missing."],
                    inputs={
                        "data_points": (end - start).days + 1,
                        "window_days": (end - start).days + 1,
                        "telemetry_coverage": (1.0 if model_total_runtime.get(model_name, 0.0) > 0 else 0.6),
                    },
                )
                if include_explain
                else None
            ),
        )
        for model_name in model_job_count.keys()
    ]
    cost_by_model.sort(key=lambda x: x.total_cost_usd, reverse=True)
    record_api_usage(db, team_id=team_id, endpoint="analytics_cost_by_model")
    if include_explain:
        point_explain = {item.model_name: item.explain for item in cost_by_model if item.explain is not None}
        return CostByModelEnvelope(
            items=cost_by_model,
            explain=explain_metric(
                value=round(sum(model_costs.values()), 2),
                unit="USD",
                window=f"{start.isoformat()} to {end.isoformat()}",
                formula="sum(daily_cost * runtime_share) across models",
                components=[
                    Component(
                        name="total_cost",
                        value=round(sum(model_costs.values()), 2),
                        unit="USD",
                        source="cost_snapshots",
                    ),
                    Component(
                        name="total_runtime_seconds",
                        value=round(total_runtime, 2),
                        unit="seconds",
                        source="jobs",
                    ),
                ],
                assumptions=["Runtime share falls back to job-count share when runtime missing."],
                inputs={
                    "data_points": (end - start).days + 1,
                    "window_days": (end - start).days + 1,
                    "telemetry_coverage": 1.0 if total_runtime > 0 else 0.6,
                },
            ),
            point_explain=point_explain,
        )
    return cost_by_model


@router.get(
    "/cost/by-team",
    response_model=Union[List[CostByTeamResponse], CostByTeamEnvelope],
    summary="Get cost aggregated by team",
)
def get_cost_by_team(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
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
            detail="end_date must be >= start_date",
        )

    team_id = get_effective_team_id(team_api_key)

    team_record = db.query(Team).filter(Team.id == team_id).first()
    if not team_record:
        return []

    job_count = (
        db.execute(
            select(func.count(Job.id)).where(
                Job.team_id == team_id,
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end,
            )
        ).scalar_one_or_none()
        or 0
    )

    total_cost = (
        db.execute(
            select(func.sum(CostSnapshot.cost_usd)).where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
        ).scalar_one_or_none()
        or 0.0
    )

    cost_by_team = [
        CostByTeamResponse(
            team_name=team_record.name,
            team_id=str(team_id),
            total_cost_usd=round(float(total_cost), 2),
            job_count=int(job_count),
            start_date=start,
            end_date=end,
            cost_share=1.0 if float(total_cost) > 0 else 0.0,
            explain=(
                explain_metric(
                    value=round(float(total_cost), 2),
                    unit="USD",
                    window=f"{start.isoformat()} to {end.isoformat()}",
                    formula="sum(cost_usd) across cost snapshots in window",
                    components=[
                        Component(
                            name="total_cost",
                            value=round(float(total_cost), 2),
                            unit="USD",
                            source="cost_snapshots",
                        ),
                        Component(
                            name="job_count",
                            value=int(job_count),
                            unit="jobs",
                            source="jobs",
                        ),
                    ],
                    assumptions=["Cost snapshots are scoped to the authenticated team."],
                    inputs={
                        "data_points": (end - start).days + 1,
                        "window_days": (end - start).days + 1,
                        "telemetry_coverage": 1.0 if int(job_count) > 0 else 0.6,
                    },
                )
                if include_explain
                else None
            ),
        )
    ]

    record_api_usage(db, team_id=team_id, endpoint="analytics_cost_by_team")
    if include_explain:
        point_explain = {item.team_name: item.explain for item in cost_by_team if item.explain is not None}
        return CostByTeamEnvelope(
            items=cost_by_team,
            explain=explain_metric(
                value=round(float(total_cost), 2),
                unit="USD",
                window=f"{start.isoformat()} to {end.isoformat()}",
                formula="sum(cost_usd) across cost snapshots in window",
                components=[
                    Component(
                        name="total_cost",
                        value=round(float(total_cost), 2),
                        unit="USD",
                        source="cost_snapshots",
                    ),
                    Component(
                        name="job_count",
                        value=int(job_count),
                        unit="jobs",
                        source="jobs",
                    ),
                ],
                assumptions=["Cost snapshots are scoped to the authenticated team."],
                inputs={
                    "data_points": (end - start).days + 1,
                    "window_days": (end - start).days + 1,
                    "telemetry_coverage": 1.0 if int(job_count) > 0 else 0.6,
                },
            ),
            point_explain=point_explain,
        )
    return cost_by_team


@router.get(
    "/savings/summary",
    response_model=SavingsSummaryResponse,
    summary="Get savings summary for a team",
)
def get_savings_summary(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
) -> Any:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )
    team_id = get_effective_team_id(team_api_key)

    # Total spend
    total_cost = (
        db.execute(
            select(func.sum(CostSnapshot.cost_usd)).where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
        ).scalar_one_or_none()
        or 0.0
    )
    total_cost = float(total_cost)

    days = (end - start).days + 1
    # Estimate idle waste: compare expected hours (24h/day) to actual usage
    cost_stmt = (
        select(
            CostSnapshot.gpu_type,
            CostSnapshot.provider,
            func.sum(CostSnapshot.cost_usd).label("total_cost"),
            func.count(CostSnapshot.id).label("days_count"),
        )
        .where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date >= start,
            CostSnapshot.date <= end,
        )
        .group_by(CostSnapshot.gpu_type, CostSnapshot.provider)
    )
    idle_waste = 0.0
    total_expected_hours = 0.0
    total_usage_hours = 0.0
    for gpu_type, provider, cost_sum, days_count in db.execute(cost_stmt).all():
        expected_hours = float(days_count) * 24.0
        usage_hours = (
            db.execute(
                select(func.sum(UsageSnapshot.gpu_hours)).where(
                    UsageSnapshot.team_id == team_id,
                    UsageSnapshot.date >= start,
                    UsageSnapshot.date <= end,
                    UsageSnapshot.gpu_type == gpu_type,
                    UsageSnapshot.provider == provider,
                )
            ).scalar_one_or_none()
            or 0.0
        )
        total_expected_hours += expected_hours
        total_usage_hours += float(usage_hours)
        if expected_hours > 0:
            waste_ratio = max(0.0, (expected_hours - float(usage_hours)) / expected_hours)
            idle_waste += float(cost_sum or 0.0) * waste_ratio

    # Recommended savings based on recommendations
    filters = RecommendationFilters(start_date=start, end_date=end, team_id=team_id)
    recs = RecommendationEngine(db).generate_recommendations(filters)
    recommended_savings = float(recs.total_estimated_savings_usd)

    response = SavingsSummaryResponse(
        start_date=start,
        end_date=end,
        total_spend_usd=round(total_cost, 2),
        estimated_idle_waste_usd=round(idle_waste, 2),
        recommended_savings_usd=round(recommended_savings, 2),
    )
    if include_explain:
        window_label = f"{start.isoformat()} to {end.isoformat()}"
        response.total_spend_explain = explain_metric(
            value=round(total_cost, 2),
            unit="USD",
            window=window_label,
            formula="sum(cost_usd) across cost snapshots in window",
            components=[
                Component(
                    name="cost_snapshot_sum",
                    value=round(total_cost, 2),
                    unit="USD",
                    source="cost_snapshots",
                ),
            ],
            assumptions=["Cost snapshots are complete for the selected window."],
            inputs={
                "data_points": int(days),
                "window_days": int(days),
            },
        )
        response.idle_waste_explain = explain_metric(
            value=round(idle_waste, 2),
            unit="USD",
            window=window_label,
            formula="sum(cost_usd * idle_ratio), idle_ratio = max(0, (expected_hours - usage_hours)/expected_hours)",
            components=[
                Component(
                    name="expected_hours",
                    value=round(total_expected_hours, 2),
                    unit="hours",
                    source="assumption",
                ),
                Component(
                    name="usage_hours",
                    value=round(total_usage_hours, 2),
                    unit="hours",
                    source="usage_snapshots",
                ),
            ],
            assumptions=["Expected hours = 24h/day per GPU type/provider."],
            inputs={
                "data_points": int(days),
                "window_days": int(days),
                "telemetry_coverage": ((total_usage_hours / total_expected_hours) if total_expected_hours else 0.0),
            },
        )
        response.recommended_savings_explain = explain_metric(
            value=round(recommended_savings, 2),
            unit="USD",
            window=window_label,
            formula="sum(recommendation.savings_estimate) for window",
            components=[
                Component(
                    name="recommendation_savings_sum",
                    value=round(recommended_savings, 2),
                    unit="USD",
                    source="recommendations",
                ),
            ],
            assumptions=["Recommendations are deterministic for the window."],
            inputs={
                "data_points": len(recs.recommendations),
                "window_days": int(days),
                "telemetry_coverage": 1.0 if recs.recommendations else 0.6,
            },
        )
    return response


@router.get("/roi", response_model=ROIDashboardResponse, summary="Get ROI / savings dashboard")
def get_roi_dashboard_endpoint(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    include_anomalies: bool = Query(True, description="Include anomaly count"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
) -> Any:
    """
    ROI / savings dashboard for business value visibility.

    Returns total spend, estimated potential savings by category,
    top recommendations, provider breakdown, and anomaly count.
    All savings are estimated; realized savings tracking is not yet implemented.
    """
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )
    team_id = get_effective_team_id(team_api_key)
    record_api_usage(db, team_id=team_id, endpoint="analytics_roi")
    return get_roi_dashboard(
        db,
        team_id=team_id,
        start_date=start,
        end_date=end,
        include_anomaly_count=include_anomalies,
    )


@router.get("/spend", response_model=MetricValue, summary="Get total spend with explainability")
def get_total_spend(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
) -> Any:
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    team_id = get_effective_team_id(team_api_key)
    total_cost = (
        db.execute(
            select(func.sum(CostSnapshot.cost_usd)).where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
        ).scalar_one_or_none()
        or 0.0
    )
    days = (end - start).days + 1
    return explain_metric(
        value=round(float(total_cost), 2),
        unit="USD",
        window=f"{start.isoformat()} to {end.isoformat()}",
        formula="sum(cost_usd) across cost snapshots in window",
        components=[
            Component(
                name="cost_snapshot_sum",
                value=round(float(total_cost), 2),
                unit="USD",
                source="cost_snapshots",
            ),
        ],
        assumptions=["Cost snapshots are complete for the selected window."],
        inputs={"data_points": int(days), "window_days": int(days)},
    )


@router.get(
    "/idle-waste",
    response_model=MetricValue,
    summary="Get idle waste with explainability",
)
def get_idle_waste(
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
) -> Any:
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    team_id = get_effective_team_id(team_api_key)
    cost_stmt = (
        select(
            CostSnapshot.gpu_type,
            CostSnapshot.provider,
            func.sum(CostSnapshot.cost_usd).label("cost_sum"),
            func.count(CostSnapshot.id).label("days_count"),
        )
        .where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date >= start,
            CostSnapshot.date <= end,
        )
        .group_by(CostSnapshot.gpu_type, CostSnapshot.provider)
    )
    idle_waste = 0.0
    for gpu_type, provider, cost_sum, days_count in db.execute(cost_stmt).all():
        expected_hours = float(days_count) * 24.0
        usage_hours = (
            db.execute(
                select(func.sum(UsageSnapshot.gpu_hours)).where(
                    UsageSnapshot.team_id == team_id,
                    UsageSnapshot.date >= start,
                    UsageSnapshot.date <= end,
                    UsageSnapshot.provider == provider,
                    UsageSnapshot.gpu_type == gpu_type,
                )
            ).scalar_one_or_none()
            or 0.0
        )
        if expected_hours > 0:
            waste_ratio = max(0.0, (expected_hours - float(usage_hours)) / expected_hours)
            idle_waste += float(cost_sum or 0.0) * waste_ratio

    days = (end - start).days + 1
    return explain_metric(
        value=round(idle_waste, 2),
        unit="USD",
        window=f"{start.isoformat()} to {end.isoformat()}",
        formula="sum(cost_usd * idle_ratio), idle_ratio = max(0, (expected_hours - usage_hours)/expected_hours)",
        components=[
            Component(
                name="idle_waste",
                value=round(idle_waste, 2),
                unit="USD",
                source="cost_snapshots",
            ),
        ],
        assumptions=["Expected hours = 24h/day per GPU type/provider."],
        inputs={
            "data_points": int(days),
            "window_days": int(days),
            "telemetry_coverage": 1.0 if idle_waste > 0 else 0.6,
        },
    )


@router.post(
    "/business-metrics",
    response_model=list[BusinessMetricResponse],
    summary="Ingest business KPI metrics",
)
def ingest_business_metrics(
    payload: BusinessMetricIngestRequest,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    results = []
    for metric in payload.metrics:
        existing = (
            db.query(BusinessMetric)
            .filter(BusinessMetric.team_id == team_id, BusinessMetric.date == metric.date)
            .first()
        )
        if existing:
            existing.revenue_usd = metric.revenue_usd
            existing.active_users = metric.active_users
            existing.requests = metric.requests
            results.append(existing)
        else:
            record = BusinessMetric(
                team_id=team_id,
                date=metric.date,
                revenue_usd=metric.revenue_usd,
                active_users=metric.active_users,
                requests=metric.requests,
            )
            db.add(record)
            results.append(record)
    db.commit()
    record_api_usage(db, team_id=team_id, endpoint="business_metrics_ingest")
    return results


@router.get(
    "/business-efficiency",
    response_model=BusinessEfficiencyResponse,
    summary="Get cost to business KPI efficiency",
)
def get_business_efficiency(
    start: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    window_days: int = Query(7, ge=1, le=30, description="Smoothing window in days"),
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
) -> Any:
    if end and start and end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )
    end_date = end or date.today()
    start_date = start or (end_date - timedelta(days=30))
    team_id = get_effective_team_id(team_api_key)

    total_cost = (
        db.execute(
            select(func.sum(CostSnapshot.cost_usd)).where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start_date,
                CostSnapshot.date <= end_date,
            )
        ).scalar_one_or_none()
        or 0.0
    )

    total_revenue = (
        db.execute(
            select(func.sum(BusinessMetric.revenue_usd)).where(
                BusinessMetric.team_id == team_id,
                BusinessMetric.date >= start_date,
                BusinessMetric.date <= end_date,
            )
        ).scalar_one_or_none()
        or 0.0
    )

    avg_active_users = (
        db.execute(
            select(func.avg(BusinessMetric.active_users)).where(
                BusinessMetric.team_id == team_id,
                BusinessMetric.date >= start_date,
                BusinessMetric.date <= end_date,
            )
        ).scalar_one_or_none()
        or 0.0
    )

    total_cost = float(total_cost)
    total_revenue = float(total_revenue)
    avg_active_users = float(avg_active_users)

    revenue_per_gpu_dollar = round(total_revenue / total_cost, 4) if total_cost > 0 else 0.0
    cost_per_active_user = round(total_cost / avg_active_users, 4) if avg_active_users > 0 else 0.0

    metrics_rows = db.execute(
        select(
            BusinessMetric.date,
            BusinessMetric.revenue_usd,
            BusinessMetric.active_users,
            BusinessMetric.requests,
        )
        .where(
            BusinessMetric.team_id == team_id,
            BusinessMetric.date >= start_date,
            BusinessMetric.date <= end_date,
        )
        .order_by(BusinessMetric.date)
    ).all()
    metrics_by_date = {
        row.date: {
            "revenue": float(row.revenue_usd or 0.0),
            "users": float(row.active_users or 0.0),
            "requests": float(row.requests or 0.0),
        }
        for row in metrics_rows
    }
    cost_rows = db.execute(
        select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd))
        .where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date >= start_date,
            CostSnapshot.date <= end_date,
        )
        .group_by(CostSnapshot.date)
    ).all()
    cost_by_date = {row[0]: float(row[1] or 0.0) for row in cost_rows}

    trends = []
    current_date = start_date
    while current_date <= end_date:
        metric = metrics_by_date.get(current_date, {"revenue": 0.0, "users": 0.0, "requests": 0.0})
        daily_cost = cost_by_date.get(current_date, 0.0)
        revenue = metric["revenue"]
        users = metric["users"]
        requests = metric["requests"]
        revenue_per_gpu_dollar = round(revenue / daily_cost, 4) if daily_cost > 0 else 0.0
        cost_per_active_user = round(daily_cost / users, 4) if users > 0 else 0.0
        requests_per_gpu_dollar = round(requests / daily_cost, 4) if daily_cost > 0 else 0.0
        trends.append(
            BusinessEfficiencyTrend(
                date=current_date,
                revenue_per_gpu_dollar=revenue_per_gpu_dollar,
                cost_per_active_user=cost_per_active_user,
                requests_per_gpu_dollar=requests_per_gpu_dollar,
                revenue_per_gpu_dollar_smoothed=revenue_per_gpu_dollar,
                cost_per_active_user_smoothed=cost_per_active_user,
                requests_per_gpu_dollar_smoothed=requests_per_gpu_dollar,
            )
        )
        current_date += timedelta(days=1)

    window = window_days
    for idx, item in enumerate(trends):
        start_idx = max(0, idx - window + 1)
        window_items = trends[start_idx : idx + 1]
        if not window_items:
            continue
        item.revenue_per_gpu_dollar_smoothed = round(
            sum(t.revenue_per_gpu_dollar for t in window_items) / len(window_items), 4
        )
        item.cost_per_active_user_smoothed = round(
            sum(t.cost_per_active_user for t in window_items) / len(window_items), 4
        )
        item.requests_per_gpu_dollar_smoothed = round(
            sum(t.requests_per_gpu_dollar for t in window_items) / len(window_items), 4
        )

    response = BusinessEfficiencyResponse(
        start_date=start_date,
        end_date=end_date,
        revenue_per_gpu_dollar=revenue_per_gpu_dollar,
        cost_per_active_user=cost_per_active_user,
        efficiency_trends=trends,
    )
    if include_explain:
        window_label = f"{start_date.isoformat()} to {end_date.isoformat()}"
        response.revenue_per_gpu_dollar_explain = explain_metric(
            value=round(revenue_per_gpu_dollar, 4),
            unit="ratio",
            window=window_label,
            formula="total_revenue / total_cost",
            components=[
                Component(
                    name="total_revenue",
                    value=round(total_revenue, 2),
                    unit="USD",
                    source="business_metrics",
                ),
                Component(
                    name="total_cost",
                    value=round(total_cost, 2),
                    unit="USD",
                    source="cost_snapshots",
                ),
            ],
            assumptions=["Revenue and cost are summed over the same window."],
            inputs={
                "data_points": (end_date - start_date).days + 1,
                "window_days": (end_date - start_date).days + 1,
                "telemetry_coverage": 1.0 if total_cost > 0 else 0.5,
            },
        )
        response.cost_per_active_user_explain = explain_metric(
            value=round(cost_per_active_user, 4),
            unit="USD",
            window=window_label,
            formula="total_cost / avg_active_users",
            components=[
                Component(
                    name="total_cost",
                    value=round(total_cost, 2),
                    unit="USD",
                    source="cost_snapshots",
                ),
                Component(
                    name="avg_active_users",
                    value=round(avg_active_users, 2),
                    unit="users",
                    source="business_metrics",
                ),
            ],
            assumptions=["Active users averaged over the window."],
            inputs={
                "data_points": (end_date - start_date).days + 1,
                "window_days": (end_date - start_date).days + 1,
                "telemetry_coverage": 1.0 if avg_active_users > 0 else 0.5,
            },
        )
    record_api_usage(db, team_id=team_id, endpoint="business_efficiency")
    return response
