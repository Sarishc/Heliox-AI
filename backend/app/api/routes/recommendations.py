"""Recommendation API endpoints for Heliox-AI."""
import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.recommendation import (
    RecommendationFilters,
    RecommendationResponse,
    RecommendationSeverity,
    RecommendationType,
)
from app.services.recommendations import RecommendationEngine

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=RecommendationResponse,
    summary="Get cost optimization recommendations",
    description="Generate rules-based recommendations for cost optimization and efficiency improvements.",
)
def get_recommendations(
    start_date: date = Query(..., description="Start date for analysis (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for analysis (YYYY-MM-DD)"),
    min_severity: RecommendationSeverity = Query(
        None, description="Filter by minimum severity (low, medium, high)"
    ),
    min_savings: float = Query(
        None, ge=0, description="Filter by minimum estimated savings (USD)"
    ),
    db: Session = Depends(get_db),
    # Public endpoint for demo - no authentication required
) -> Any:
    """
    Get cost optimization recommendations based on historical data.
    
    This endpoint analyzes job execution patterns, GPU usage, and costs
    to generate actionable recommendations for:
    - Reducing idle GPU spend
    - Optimizing long-running jobs
    - Better scheduling (off-peak hours)
    
    Query Parameters:
    - start_date: Start date for analysis (required)
    - end_date: End date for analysis (required)
    - min_severity: Filter by minimum severity level (optional)
    - min_savings: Filter by minimum estimated savings in USD (optional)
    
    Returns:
        RecommendationResponse with list of recommendations and summary statistics
        
    Raises:
        400 Bad Request: If date range is invalid
        500 Internal Server Error: If recommendation generation fails
    """
    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )
    
    # Check if date range is too large (limit to 90 days for performance)
    days_diff = (end_date - start_date).days
    if days_diff > 90:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 90 days",
        )
    
    try:
        logger.info(
            f"Generating recommendations for date range: {start_date} to {end_date}"
        )
        
        # Create filters
        filters = RecommendationFilters(
            start_date=start_date,
            end_date=end_date,
            min_severity=min_severity,
            min_savings=min_savings,
        )
        
        # Initialize recommendation engine
        engine = RecommendationEngine(db)
        
        # Generate recommendations
        result = engine.generate_recommendations(filters)
        
        logger.info(
            f"Generated {len(result.recommendations)} recommendations "
            f"with ${result.total_estimated_savings_usd:,.2f} potential savings"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations. Check server logs for details.",
        )


@router.get(
    "/summary",
    summary="Get recommendations summary",
    description="Get a quick summary of available recommendations without full details.",
)
def get_recommendations_summary(
    start_date: date = Query(..., description="Start date for analysis (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date for analysis (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get a summary of recommendations without full details.
    
    This is a lighter-weight endpoint that returns only counts and
    total savings without the full recommendation details.
    
    Query Parameters:
    - start_date: Start date for analysis (required)
    - end_date: End date for analysis (required)
    
    Returns:
        Summary statistics including counts by severity and type,
        plus total estimated savings
    """
    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )
    
    try:
        # Create filters
        filters = RecommendationFilters(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Initialize recommendation engine
        engine = RecommendationEngine(db)
        
        # Generate recommendations
        result = engine.generate_recommendations(filters)
        
        # Return only summary
        return {
            "date_range": result.date_range,
            "total_recommendations": len(result.recommendations),
            "total_estimated_savings_usd": result.total_estimated_savings_usd,
            "summary": result.summary,
        }
        
    except Exception as e:
        logger.error(f"Error generating recommendations summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations summary.",
        )


@router.get(
    "/types",
    summary="Get available recommendation types",
    description="List all available recommendation types and their descriptions.",
)
def get_recommendation_types() -> Any:
    """
    Get information about available recommendation types.
    
    Returns:
        Dictionary of recommendation types with descriptions
    """
    return {
        "types": [
            {
                "type": RecommendationType.IDLE_GPU.value,
                "name": "Idle GPU Detection",
                "description": "Identifies GPUs with low utilization where costs exceed actual usage",
            },
            {
                "type": RecommendationType.LONG_RUNNING_JOB.value,
                "name": "Long-Running Jobs",
                "description": "Flags jobs that run for extended periods and may benefit from optimization",
            },
            {
                "type": RecommendationType.OFF_HOURS_USAGE.value,
                "name": "Off-Hours Scheduling",
                "description": "Suggests moving jobs to off-peak hours for potential cost savings",
            },
            {
                "type": RecommendationType.COST_OPTIMIZATION.value,
                "name": "General Cost Optimization",
                "description": "Other cost optimization opportunities",
            },
        ]
    }

