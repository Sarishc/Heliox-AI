"""Forecast API endpoints."""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.forecast import ForecastResponse
from app.services.forecasting import ForecastingService, DEFAULT_HORIZON_DAYS, MAX_HORIZON_DAYS

logger = logging.getLogger(__name__)

router = APIRouter()


def get_redis_client():
    """Get Redis client for caching (optional)."""
    try:
        from app.core.cache import get_redis
        return get_redis()
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        return None


@router.get(
    "/usage",
    response_model=ForecastResponse,
    summary="Forecast GPU usage",
    description="Generate GPU usage forecast based on historical UsageSnapshot data. "
                "Uses moving average + trend for <30 days of data, LightGBM for >=30 days."
)
def forecast_usage(
    provider: Optional[str] = Query(
        None,
        description="Filter by provider (e.g., 'aws', 'gcp', 'azure')",
        example="aws"
    ),
    gpu_type: Optional[str] = Query(
        None,
        description="Filter by GPU type (e.g., 'a100', 'h100', 'v100')",
        example="h100"
    ),
    horizon_days: int = Query(
        DEFAULT_HORIZON_DAYS,
        ge=1,
        le=MAX_HORIZON_DAYS,
        description=f"Number of days to forecast (1-{MAX_HORIZON_DAYS})",
        example=7
    ),
    db: Session = Depends(get_db),
) -> Any:
    """
    Generate GPU usage forecast.
    
    This endpoint forecasts future GPU usage (in GPU hours) based on historical patterns.
    
    **Forecasting Method:**
    - **Moving Average + Trend**: Used when <30 days of historical data available
    - **LightGBM**: Used when >=30 days of historical data available
    
    **Confidence Bands:**
    - 95% confidence intervals based on historical volatility
    - Bands widen over forecast horizon
    
    **Caching:**
    - Results cached for 1 hour in Redis
    - Cache key includes provider, gpu_type, and horizon
    
    **Example Use Cases:**
    - Capacity planning
    - Resource allocation
    - Budget forecasting
    
    Returns:
        ForecastResponse with historical data, forecast points, and confidence intervals
        
    Raises:
        400 Bad Request: If insufficient historical data (<7 days)
        500 Internal Server Error: If forecast generation fails
    """
    try:
        redis_client = get_redis_client()
        forecast_service = ForecastingService(db, redis_client)
        
        result = forecast_service.forecast_usage(
            provider=provider,
            gpu_type=gpu_type,
            horizon_days=horizon_days
        )
        
        if result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating usage forecast: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate usage forecast: {str(e)}"
        )


@router.get(
    "/spend",
    response_model=ForecastResponse,
    summary="Forecast GPU spending",
    description="Generate GPU cost forecast based on historical CostSnapshot data. "
                "Uses moving average + trend for <30 days of data, LightGBM for >=30 days."
)
def forecast_spend(
    provider: Optional[str] = Query(
        None,
        description="Filter by provider (e.g., 'aws', 'gcp', 'azure')",
        example="aws"
    ),
    gpu_type: Optional[str] = Query(
        None,
        description="Filter by GPU type (e.g., 'a100', 'h100', 'v100')",
        example="h100"
    ),
    horizon_days: int = Query(
        DEFAULT_HORIZON_DAYS,
        ge=1,
        le=MAX_HORIZON_DAYS,
        description=f"Number of days to forecast (1-{MAX_HORIZON_DAYS})",
        example=7
    ),
    db: Session = Depends(get_db),
) -> Any:
    """
    Generate GPU spending forecast.
    
    This endpoint forecasts future GPU costs (in USD) based on historical patterns.
    
    **Forecasting Method:**
    - **Moving Average + Trend**: Used when <30 days of historical data available
    - **LightGBM**: Used when >=30 days of historical data available
    
    **Confidence Bands:**
    - 95% confidence intervals based on historical volatility
    - Bands widen over forecast horizon
    
    **Caching:**
    - Results cached for 1 hour in Redis
    - Cache key includes provider, gpu_type, and horizon
    
    **Example Use Cases:**
    - Budget planning
    - Cost alerts
    - Financial forecasting
    - Chargeback projections
    
    Returns:
        ForecastResponse with historical data, forecast points, and confidence intervals
        
    Raises:
        400 Bad Request: If insufficient historical data (<7 days)
        500 Internal Server Error: If forecast generation fails
    """
    try:
        redis_client = get_redis_client()
        forecast_service = ForecastingService(db, redis_client)
        
        result = forecast_service.forecast_spend(
            provider=provider,
            gpu_type=gpu_type,
            horizon_days=horizon_days
        )
        
        if result.get("error"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating spend forecast: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate spend forecast: {str(e)}"
        )


@router.get(
    "/health",
    summary="Forecast service health check",
    description="Check if forecasting service is available and configured correctly."
)
def forecast_health(db: Session = Depends(get_db)) -> dict:
    """
    Health check for forecasting service.
    
    Checks:
    - Database connectivity
    - Redis availability (optional)
    - LightGBM availability (optional)
    
    Returns:
        Health status and available features
    """
    redis_client = get_redis_client()
    
    # Check LightGBM availability
    lightgbm_available = False
    try:
        import lightgbm
        lightgbm_available = True
    except ImportError:
        pass
    
    return {
        "status": "ok",
        "features": {
            "database": "connected",
            "redis_caching": "available" if redis_client else "unavailable",
            "lightgbm_ml": "available" if lightgbm_available else "unavailable (using moving average)",
            "forecast_methods": ["moving_average", "lightgbm"] if lightgbm_available else ["moving_average"]
        },
        "limits": {
            "min_data_points": 7,
            "max_horizon_days": MAX_HORIZON_DAYS,
            "default_horizon_days": DEFAULT_HORIZON_DAYS
        }
    }

