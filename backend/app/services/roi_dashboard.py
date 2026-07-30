"""
ROI / savings dashboard service.

Aggregates cost, recommendations, and anomaly data to produce
a tenant-scoped ROI view. All savings are estimated/potential.
"""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot
from app.schemas.recommendation import RecommendationFilters, RecommendationType
from app.schemas.roi import (
    ProviderBreakdown,
    ROIDashboardResponse,
    SavingsByCategory,
    TopRecommendation,
)
from app.services.recommendations import RecommendationEngine

logger = logging.getLogger(__name__)

TYPE_LABELS = {
    RecommendationType.IDLE_GPU.value: "Idle GPU spend",
    RecommendationType.LONG_RUNNING_JOB.value: "Long-running jobs",
    RecommendationType.OFF_HOURS_USAGE.value: "Off-hours scheduling",
    RecommendationType.COST_OPTIMIZATION.value: "Cost optimization",
}


def get_roi_dashboard(
    db: Session,
    team_id: UUID,
    start_date: date,
    end_date: date,
    include_anomaly_count: bool = True,
) -> ROIDashboardResponse:
    """
    Build ROI dashboard for a team over a date range.

    Uses existing CostSnapshot and RecommendationEngine.
    No double-counting: recommended_savings comes solely from RecommendationEngine.
    """
    days = max(0, (end_date - start_date).days + 1)
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    # Total spend
    total_spend_result = db.execute(
        select(func.sum(CostSnapshot.cost_usd)).where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date >= start_date,
            CostSnapshot.date <= end_date,
        )
    ).scalar_one_or_none()
    total_spend = float(total_spend_result or 0.0)

    # Recommendations (single source of truth for savings)
    filters = RecommendationFilters(
        start_date=start_date,
        end_date=end_date,
        team_id=team_id,
    )
    rec_engine = RecommendationEngine(db)
    rec_response = rec_engine.generate_recommendations(filters)
    recommendations = rec_response.recommendations
    total_savings = float(rec_response.total_estimated_savings_usd)

    savings_pct = (total_savings / total_spend * 100.0) if total_spend > 0 else 0.0

    # Savings by category
    by_type: dict[str, list] = {}
    for rec in recommendations:
        t = rec.type.value
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(rec)
    savings_by_category = [
        SavingsByCategory(
            type=t,
            label=TYPE_LABELS.get(t, t.replace("_", " ").title()),
            estimated_savings_usd=round(sum(r.estimated_savings_usd for r in recs), 2),
            count=len(recs),
        )
        for t, recs in by_type.items()
    ]
    savings_by_category.sort(key=lambda x: -x.estimated_savings_usd)

    # Top 5 recommendations
    sorted_recs = sorted(
        recommendations,
        key=lambda r: r.estimated_savings_usd,
        reverse=True,
    )
    top_recommendations = [
        TopRecommendation(
            title=r.title,
            type=r.type.value,
            estimated_savings_usd=round(r.estimated_savings_usd, 2),
            severity=r.severity.value,
        )
        for r in sorted_recs[:5]
    ]

    # Provider breakdown
    provider_rows = db.execute(
        select(
            CostSnapshot.provider,
            func.sum(CostSnapshot.cost_usd).label("cost"),
        )
        .where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date >= start_date,
            CostSnapshot.date <= end_date,
        )
        .group_by(CostSnapshot.provider)
    ).all()
    provider_breakdown = []
    for provider, cost in provider_rows:
        cost_f = float(cost or 0)
        share = (cost_f / total_spend * 100.0) if total_spend > 0 else 0.0
        provider_breakdown.append(
            ProviderBreakdown(
                provider=provider or "unknown",
                cost_usd=round(cost_f, 2),
                share_percent=round(share, 1),
            )
        )
    provider_breakdown.sort(key=lambda x: -x.cost_usd)

    # Anomaly count (optional, can be expensive)
    anomaly_count = 0
    if include_anomaly_count:
        try:
            from app.services.anomaly import AnomalyDetectionService

            anomaly_result = AnomalyDetectionService(db).detect(team_id=team_id)
            anomaly_count = len(anomaly_result.anomalies)
        except Exception as e:
            logger.warning(f"Could not fetch anomaly count for ROI: {e}")

    return ROIDashboardResponse(
        start_date=start_date,
        end_date=end_date,
        total_spend_usd=round(total_spend, 2),
        estimated_potential_savings_usd=round(total_savings, 2),
        savings_percent_of_spend=round(min(100.0, max(0.0, savings_pct)), 1),
        savings_by_category=savings_by_category,
        top_recommendations=top_recommendations,
        provider_breakdown=provider_breakdown,
        anomaly_count=anomaly_count,
        recommendation_count=len(recommendations),
        disclaimer="All savings are estimated potential. Actual savings depend on implementation.",
    )
