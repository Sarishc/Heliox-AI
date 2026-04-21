"""Tests for weekly report service."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.cost import CostSnapshot
from app.services.weekly_report import get_weekly_report_data, WeeklyReportData


@pytest.fixture
def team(db_session: Session) -> Team:
    t = Team(name="Weekly Report Test Team")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def test_weekly_report_data_structure(db_session: Session, team: Team):
    """Weekly report returns all required fields."""
    report = get_weekly_report_data(db_session, team.id)
    assert report is not None
    assert isinstance(report, WeeklyReportData)
    assert report.team_id == team.id
    assert report.team_name == team.name
    assert report.start_date <= report.end_date
    assert (report.end_date - report.start_date).days == 6
    assert report.total_spend_usd >= 0
    assert report.estimated_potential_savings_usd >= 0
    assert report.savings_percent_of_spend >= 0
    assert isinstance(report.top_recommendations, list)
    assert isinstance(report.provider_breakdown, list)
    assert report.anomaly_count >= 0
    assert report.idle_savings_usd >= 0
    assert report.dashboard_url
    assert "/roi" in report.dashboard_url or "heliox" in report.dashboard_url.lower()


def test_weekly_report_tenant_scoped(db_session: Session, team: Team):
    """Weekly report is scoped to team."""
    other = Team(name="Other Team")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    report = get_weekly_report_data(db_session, other.id)
    assert report is not None
    assert report.team_id == other.id
    assert report.team_name == other.name
    assert report.total_spend_usd == 0


def test_weekly_report_with_cost_data(db_session: Session, team: Team):
    """Weekly report includes cost when data exists."""
    base = date.today() - timedelta(days=3)
    for i in range(3):
        d = base + timedelta(days=i)
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=d,
                provider="AWS",
                gpu_type="A100",
                cost_usd=Decimal("200.00"),
            )
        )
    db_session.commit()
    report = get_weekly_report_data(db_session, team.id)
    assert report is not None
    assert report.total_spend_usd == 600.0
    assert any(p.get("provider") == "AWS" for p in report.provider_breakdown)


def test_weekly_report_no_sensitive_data(db_session: Session, team: Team):
    """Report does not expose sensitive data (no API keys, webhooks, emails)."""
    report = get_weekly_report_data(db_session, team.id)
    assert report is not None
    # WeeklyReportData has no secret fields - only team_name, costs, recommendations, dashboard_url
    assert hasattr(report, "team_name")
    assert hasattr(report, "dashboard_url")
    assert "re_" not in report.dashboard_url  # No Resend IDs
    assert "hooks.slack" not in report.dashboard_url
