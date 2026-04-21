"""
Weekly report generation service.

Produces a team-scoped weekly summary for proactive value delivery.
Reuses ROI dashboard and analytics data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.roi_dashboard import get_roi_dashboard

logger = logging.getLogger(__name__)


@dataclass
class WeeklyReportData:
    """Payload for weekly report email/Slack."""

    team_id: UUID
    team_name: str
    start_date: date
    end_date: date
    total_spend_usd: float
    estimated_potential_savings_usd: float
    savings_percent_of_spend: float
    top_recommendations: List[dict]  # top 3: title, type, estimated_savings_usd
    provider_breakdown: List[dict]  # provider, cost_usd, share_percent
    anomaly_count: int
    idle_savings_usd: float  # from idle_gpu category
    dashboard_url: str


def get_weekly_report_data(
    db: Session,
    team_id: UUID,
    *,
    dashboard_base_url: Optional[str] = None,
) -> Optional[WeeklyReportData]:
    """
    Generate weekly report data for a team (last 7 days).

    Returns None if team has no meaningful data (e.g. no spend).
    Still returns data with zeros for teams with alerts enabled
    so they get a "nothing to report" style email.
    """
    from app.core.config import get_settings
    from app.models.team import Team

    settings = get_settings()
    end_date = date.today()
    start_date = end_date - timedelta(days=6)  # 7 days inclusive

    roi = get_roi_dashboard(
        db,
        team_id=team_id,
        start_date=start_date,
        end_date=end_date,
        include_anomaly_count=True,
    )

    team = db.query(Team).filter(Team.id == team_id).first()
    team_name = team.name if team else "Your Team"

    base_url = (dashboard_base_url or settings.FRONTEND_URL or "").rstrip("/")
    dashboard_url = f"{base_url}/roi" if base_url else "https://app.heliox.ai/roi"

    idle_savings = 0.0
    for cat in roi.savings_by_category:
        if cat.type == "idle_gpu":
            idle_savings = cat.estimated_savings_usd
            break

    top_3 = [
        {
            "title": r.title,
            "type": r.type,
            "estimated_savings_usd": r.estimated_savings_usd,
        }
        for r in roi.top_recommendations[:3]
    ]

    providers = [
        {
            "provider": p.provider,
            "cost_usd": p.cost_usd,
            "share_percent": p.share_percent,
        }
        for p in roi.provider_breakdown
    ]

    return WeeklyReportData(
        team_id=team_id,
        team_name=team_name,
        start_date=start_date,
        end_date=end_date,
        total_spend_usd=roi.total_spend_usd,
        estimated_potential_savings_usd=roi.estimated_potential_savings_usd,
        savings_percent_of_spend=roi.savings_percent_of_spend,
        top_recommendations=top_3,
        provider_breakdown=providers,
        anomaly_count=roi.anomaly_count,
        idle_savings_usd=idle_savings,
        dashboard_url=dashboard_url,
    )
