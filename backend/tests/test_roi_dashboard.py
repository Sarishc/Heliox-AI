"""Tests for ROI / savings dashboard."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.cost import CostSnapshot
from app.services.roi_dashboard import get_roi_dashboard


@pytest.fixture
def team(db_session: Session) -> Team:
    t = Team(name="ROI Test Team")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def cost_data(db_session: Session, team: Team):
    """Create cost snapshots for a team over 14 days."""
    base = date.today() - timedelta(days=14)
    for i in range(14):
        d = base + timedelta(days=i)
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=d,
                provider="AWS",
                gpu_type="A100",
                cost_usd=Decimal("100.00"),
            )
        )
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=d,
                provider="GCP",
                gpu_type="V100",
                cost_usd=Decimal("50.00"),
            )
        )
    db_session.commit()


def test_roi_empty_team(db_session: Session, team: Team):
    """ROI with no cost data returns zeros."""
    start = date.today() - timedelta(days=14)
    end = date.today()
    r = get_roi_dashboard(db_session, team.id, start, end, include_anomaly_count=False)
    assert r.total_spend_usd == 0
    assert r.estimated_potential_savings_usd == 0
    assert r.savings_percent_of_spend == 0
    assert r.recommendation_count >= 0
    assert r.disclaimer


def test_roi_with_cost_no_usage(db_session: Session, team: Team, cost_data):
    """ROI with cost but no usage can still show spend and may have idle recommendations."""
    start = date.today() - timedelta(days=14)
    end = date.today()
    r = get_roi_dashboard(db_session, team.id, start, end, include_anomaly_count=False)
    # 14 days * (100 + 50) = 2100
    assert r.total_spend_usd == 2100.0
    assert r.provider_breakdown
    aws = next((p for p in r.provider_breakdown if p.provider == "AWS"), None)
    assert aws is not None
    assert aws.cost_usd == 1400.0  # 14 * 100
    gcp = next((p for p in r.provider_breakdown if p.provider == "GCP"), None)
    assert gcp is not None
    assert gcp.cost_usd == 700.0


def test_roi_tenant_scoped(db_session: Session, team: Team, cost_data):
    """ROI is scoped to team - other team gets no data."""
    other_team = Team(name="Other Team")
    db_session.add(other_team)
    db_session.commit()
    db_session.refresh(other_team)
    start = date.today() - timedelta(days=14)
    end = date.today()
    r = get_roi_dashboard(db_session, other_team.id, start, end, include_anomaly_count=False)
    assert r.total_spend_usd == 0


def test_roi_date_range_validation(db_session: Session, team: Team):
    """ROI handles reversed date range."""
    start = date.today()
    end = date.today() - timedelta(days=7)
    r = get_roi_dashboard(db_session, team.id, start, end, include_anomaly_count=False)
    # Service swaps if end < start
    assert r.start_date <= r.end_date
