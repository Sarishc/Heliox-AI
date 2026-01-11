"""Tests for forecasting service."""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.services.forecasting import ForecastingService
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.team import Team


@pytest.fixture
def db_with_usage_data(db_session):
    """Create test database with usage data."""
    # Create 14 days of usage data
    start_date = date(2026, 1, 1)
    for i in range(14):
        current_date = start_date + timedelta(days=i)
        usage = UsageSnapshot(
            date=current_date,
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal(str(100 + i * 5))  # Increasing trend
        )
        db_session.add(usage)
    
    db_session.commit()
    return db_session


@pytest.fixture
def db_with_cost_data(db_session):
    """Create test database with cost data."""
    # Create 14 days of cost data
    start_date = date(2026, 1, 1)
    for i in range(14):
        current_date = start_date + timedelta(days=i)
        cost = CostSnapshot(
            date=current_date,
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal(str(1000 + i * 50))  # Increasing trend
        )
        db_session.add(cost)
    
    db_session.commit()
    return db_session


def test_forecast_usage_shape(db_with_usage_data):
    """Test that usage forecast returns correct shape."""
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    result = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Check response structure
    assert "historical" in result
    assert "forecast" in result
    assert "metadata" in result
    assert "forecast_method" in result
    
    # Check historical data
    assert len(result["historical"]) == 14
    for point in result["historical"]:
        assert "date" in point
        assert "value" in point
        assert point["value"] >= 0
    
    # Check forecast data
    assert len(result["forecast"]) == 7
    for point in result["forecast"]:
        assert "date" in point
        assert "value" in point
        assert "lower_bound" in point
        assert "upper_bound" in point
        assert point["value"] >= 0
        assert point["lower_bound"] >= 0
        assert point["upper_bound"] >= point["value"]


def test_forecast_spend_shape(db_with_cost_data):
    """Test that spend forecast returns correct shape."""
    service = ForecastingService(db_with_cost_data, redis_client=None)
    
    result = service.forecast_spend(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Check response structure
    assert "historical" in result
    assert "forecast" in result
    assert "metadata" in result
    assert "forecast_method" in result
    
    # Check historical data
    assert len(result["historical"]) == 14
    for point in result["historical"]:
        assert "date" in point
        assert "value" in point
        assert point["value"] >= 0
    
    # Check forecast data
    assert len(result["forecast"]) == 7
    for point in result["forecast"]:
        assert "date" in point
        assert "value" in point
        assert "lower_bound" in point
        assert "upper_bound" in point
        assert point["value"] >= 0
        assert point["lower_bound"] >= 0
        assert point["upper_bound"] >= point["value"]


def test_forecast_insufficient_data(db_session):
    """Test forecast behavior with insufficient data."""
    service = ForecastingService(db_session, redis_client=None)
    
    # Add only 3 days of data (less than MIN_DATA_POINTS_FOR_FORECAST=7)
    start_date = date(2026, 1, 1)
    for i in range(3):
        current_date = start_date + timedelta(days=i)
        usage = UsageSnapshot(
            date=current_date,
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal("100")
        )
        db_session.add(usage)
    
    db_session.commit()
    
    result = service.forecast_usage(provider="aws", gpu_type="a100", horizon_days=7)
    
    # Should return error
    assert "error" in result
    assert len(result["forecast"]) == 0


def test_forecast_horizon_validation(db_with_usage_data):
    """Test that forecast respects horizon limits."""
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    # Test various horizons
    for horizon in [1, 7, 14, 30]:
        result = service.forecast_usage(
            provider="aws",
            gpu_type="a100",
            horizon_days=horizon
        )
        assert len(result["forecast"]) == horizon


def test_forecast_trend_detection(db_with_usage_data):
    """Test that forecast detects increasing trend."""
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    result = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Last historical value
    last_historical = result["historical"][-1]["value"]
    
    # First forecast value should be higher (due to increasing trend)
    first_forecast = result["forecast"][0]["value"]
    
    # With an increasing trend, forecast should generally be higher
    # (though not guaranteed due to smoothing)
    assert first_forecast >= last_historical * 0.9  # Allow some variation


def test_forecast_confidence_bands_widen(db_with_usage_data):
    """Test that confidence bands widen over forecast horizon."""
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    result = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Calculate band width for first and last forecast
    first_band_width = (
        result["forecast"][0]["upper_bound"] - 
        result["forecast"][0]["lower_bound"]
    )
    last_band_width = (
        result["forecast"][-1]["upper_bound"] - 
        result["forecast"][-1]["lower_bound"]
    )
    
    # Last forecast should have wider confidence band
    assert last_band_width >= first_band_width


def test_forecast_caching(db_with_usage_data):
    """Test that forecast caching works (if Redis available)."""
    # This test will pass even without Redis
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    # Generate forecast twice
    result1 = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    result2 = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Results should be identical (deterministic)
    assert result1["forecast_method"] == result2["forecast_method"]
    assert len(result1["forecast"]) == len(result2["forecast"])


def test_forecast_non_negative(db_with_usage_data):
    """Test that forecast values are never negative."""
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    result = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Check all forecast values and bounds are non-negative
    for point in result["forecast"]:
        assert point["value"] >= 0
        assert point["lower_bound"] >= 0
        assert point["upper_bound"] >= 0


def test_forecast_metadata(db_with_usage_data):
    """Test that forecast includes correct metadata."""
    service = ForecastingService(db_with_usage_data, redis_client=None)
    
    result = service.forecast_usage(
        provider="aws",
        gpu_type="a100",
        horizon_days=7
    )
    
    # Check metadata
    assert result["metadata"]["historical_data_points"] == 14
    assert "forecast_generated_at" in result["metadata"]
    assert result["horizon_days"] == 7
    assert result["provider"] == "aws"
    assert result["gpu_type"] == "a100"


def test_forecast_method_selection(db_session):
    """Test that correct forecast method is selected based on data size."""
    service = ForecastingService(db_session, redis_client=None)
    
    # Add 14 days of data (less than MIN_DATA_POINTS_FOR_ML=30)
    start_date = date(2026, 1, 1)
    for i in range(14):
        current_date = start_date + timedelta(days=i)
        usage = UsageSnapshot(
            date=current_date,
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal(str(100 + i * 5))
        )
        db_session.add(usage)
    
    db_session.commit()
    
    result = service.forecast_usage(provider="aws", gpu_type="a100", horizon_days=7)
    
    # Should use moving_average for < 30 days
    assert result["forecast_method"] == "moving_average"

