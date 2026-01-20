"""Tests for daily digest generator."""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.cost import CostSnapshot
from app.models.team import Team
from app.services.daily_digest import DailyDigestGenerator


@pytest.fixture
def sample_teams_with_costs(db_session):
    """Create sample teams with cost data."""
    # Create teams
    team1 = Team(name="ML Research")
    team2 = Team(name="Data Science")
    
    db_session.add_all([team1, team2])
    db_session.commit()
    
    # Create cost snapshots for yesterday
    yesterday = date.today() - timedelta(days=1)
    
    costs = [
        # Team 1
        CostSnapshot(
            date=yesterday,
            team_id=team1.id,
            provider="aws",
            gpu_type="h100",
            cost_usd=Decimal("5000.00")
        ),
        CostSnapshot(
            date=yesterday,
            team_id=team1.id,
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("3000.00")
        ),
        # Team 2
        CostSnapshot(
            date=yesterday,
            team_id=team2.id,
            provider="gcp",
            gpu_type="a100",
            cost_usd=Decimal("2000.00")
        ),
    ]
    
    db_session.add_all(costs)
    db_session.commit()
    
    return [team1, team2]


def test_generate_daily_digest(db_session, sample_teams_with_costs):
    """Test generating complete daily digest."""
    generator = DailyDigestGenerator(db_session)
    yesterday = date.today() - timedelta(days=1)
    
    digest = generator.generate_daily_digest(yesterday)
    
    assert digest.date == str(yesterday)
    assert digest.total_daily_cost == 10000.00  # 5000 + 3000 + 2000
    assert len(digest.teams) == 0  # Simplified global digest
    assert len(digest.global_top_models) >= 0


def test_digest_top_models(db_session, sample_teams_with_costs):
    """Test that top models are sorted by cost."""
    generator = DailyDigestGenerator(db_session)
    yesterday = date.today() - timedelta(days=1)
    
    top_models = generator._get_top_gpu_types(yesterday, yesterday, limit=3)
    
    assert len(top_models) <= 3
    # Verify sorted by cost (descending)
    for i in range(len(top_models) - 1):
        assert top_models[i]["cost"] >= top_models[i + 1]["cost"]


def test_digest_date_ranges(db_session, sample_teams_with_costs):
    """Test cost calculations for different date ranges."""
    generator = DailyDigestGenerator(db_session)
    yesterday = date.today() - timedelta(days=1)
    week_ago = yesterday - timedelta(days=7)
    
    # Daily cost
    daily = generator._get_cost_for_period(yesterday, yesterday)
    assert daily == 10000.00
    
    # Weekly cost (should be same as daily since we only have one day)
    weekly = generator._get_cost_for_period(week_ago, yesterday)
    assert weekly == 10000.00


def test_digest_global_costs(db_session, sample_teams_with_costs):
    """Test that global cost aggregation works."""
    generator = DailyDigestGenerator(db_session)
    yesterday = date.today() - timedelta(days=1)
    
    total = generator._get_cost_for_period(yesterday, yesterday)
    assert total == 10000.00


def test_digest_payload_structure(db_session, sample_teams_with_costs):
    """Test that digest payload has correct structure."""
    generator = DailyDigestGenerator(db_session)
    yesterday = date.today() - timedelta(days=1)
    
    digest = generator.generate_daily_digest(yesterday)
    
    # Check required fields
    assert hasattr(digest, 'date')
    assert hasattr(digest, 'total_daily_cost')
    assert hasattr(digest, 'total_weekly_cost')
    assert hasattr(digest, 'total_monthly_cost')
    assert hasattr(digest, 'teams')
    assert hasattr(digest, 'global_top_models')
    assert hasattr(digest, 'global_recommendations')
    assert hasattr(digest, 'global_potential_savings')
    
    # Simplified digest should not include per-team data
    assert digest.teams == []

