"""Tests for alert settings."""
import pytest
from decimal import Decimal

from app.models.alert_settings import AlertSettings
from app.models.team import Team


@pytest.fixture
def sample_team(db_session):
    """Create a sample team."""
    team = Team(
        id="test-team-1",
        name="Test Team"
    )
    db_session.add(team)
    db_session.commit()
    return team


def test_create_alert_settings(db_session, sample_team):
    """Test creating alert settings."""
    settings = AlertSettings(
        team_id=sample_team.id,
        burn_rate_threshold_usd_per_day=Decimal("15000.00"),
        enable_slack=True,
        enable_email=False
    )
    
    db_session.add(settings)
    db_session.commit()
    
    # Verify
    retrieved = db_session.query(AlertSettings).filter(
        AlertSettings.team_id == sample_team.id
    ).first()
    
    assert retrieved is not None
    assert retrieved.burn_rate_threshold_usd_per_day == Decimal("15000.00")
    assert retrieved.enable_slack is True
    assert retrieved.enable_email is False


def test_alert_settings_defaults(db_session, sample_team):
    """Test default values for alert settings."""
    settings = AlertSettings(team_id=sample_team.id)
    
    db_session.add(settings)
    db_session.commit()
    
    assert settings.burn_rate_threshold_usd_per_day == Decimal("10000.00")
    assert settings.enable_slack is True
    assert settings.enable_email is False


def test_alert_settings_unique_per_team(db_session, sample_team):
    """Test that only one alert settings per team is allowed."""
    settings1 = AlertSettings(team_id=sample_team.id)
    db_session.add(settings1)
    db_session.commit()
    
    # Try to create another (should fail due to unique constraint)
    settings2 = AlertSettings(team_id=sample_team.id)
    db_session.add(settings2)
    
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_alert_settings_relationship(db_session, sample_team):
    """Test relationship between team and alert settings."""
    settings = AlertSettings(team_id=sample_team.id)
    db_session.add(settings)
    db_session.commit()
    
    # Access via relationship
    db_session.refresh(sample_team)
    assert sample_team.alert_settings is not None
    assert sample_team.alert_settings.id == settings.id


def test_delete_team_cascades_settings(db_session, sample_team):
    """Test that deleting a team deletes its alert settings."""
    settings = AlertSettings(team_id=sample_team.id)
    db_session.add(settings)
    db_session.commit()
    
    settings_id = settings.id
    
    # Delete team
    db_session.delete(sample_team)
    db_session.commit()
    
    # Verify settings are deleted
    retrieved = db_session.query(AlertSettings).filter(
        AlertSettings.id == settings_id
    ).first()
    
    assert retrieved is None

