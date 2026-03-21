"""Recommendation API endpoints for Heliox-AI."""
import logging
from datetime import date
from typing import Any, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user_optional
from app.auth.rbac import get_team_id_from_context, require_team_admin_or_api_key
from app.auth.team_resolution import TeamContext, get_team_api_key_or_session_optional
from app.core.db import get_db
from app.core.usage_tracking import record_api_usage
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.models.team_api_key import TeamAPIKey
from app.schemas.recommendation import (
    Recommendation,
    RecommendationFilters,
    RecommendationResponse,
    RecommendationSeverity,
    RecommendationType,
)
from app.services.recommendations import RecommendationEngine
from app.services.recommendation_actions import (
    apply_recommendation,
    get_action_status,
    list_actions,
    recommendation_fingerprint,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _enrich_recommendations_with_action_status(
    db: Session,
    team_id: Any,
    recommendations: list[Recommendation],
) -> list[Recommendation]:
    """Add action_status to recommendations based on stored actions."""
    if not team_id or not recommendations:
        return recommendations
    try:
        from uuid import UUID
        tid = UUID(str(team_id))
    except (ValueError, TypeError):
        return recommendations
    fingerprints = [recommendation_fingerprint(r) for r in recommendations]
    status_map = get_action_status(db, tid, fingerprints)
    enriched = []
    for rec in recommendations:
        fp = recommendation_fingerprint(rec)
        action_status = status_map.get(fp)
        enriched.append(rec.model_copy(update={"action_status": action_status}))
    return enriched


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
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
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
        
        # Create filters (enforce tenant isolation)
        team_id = get_effective_team_id(team_api_key)
        filters = RecommendationFilters(
            start_date=start_date,
            end_date=end_date,
            min_severity=min_severity,
            min_savings=min_savings,
            team_id=team_id,
        )
        
        # Initialize recommendation engine
        engine = RecommendationEngine(db)
        
        # Generate recommendations
        result = engine.generate_recommendations(filters)
        # Enrich with action status when team is known
        result.recommendations = _enrich_recommendations_with_action_status(
            db, team_id, result.recommendations
        )
        
        logger.info(
            f"Generated {len(result.recommendations)} recommendations "
            f"with ${result.total_estimated_savings_usd:,.2f} potential savings"
        )
        
        record_api_usage(db, team_id=team_id, endpoint="recommendations")
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
    team_api_key: TeamAPIKey | TeamContext | None = Depends(get_team_api_key_or_session_optional),
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
        team_id = get_effective_team_id(team_api_key)
        filters = RecommendationFilters(
            start_date=start_date,
            end_date=end_date,
            team_id=team_id,
        )
        
        # Initialize recommendation engine
        engine = RecommendationEngine(db)
        
        # Generate recommendations
        result = engine.generate_recommendations(filters)
        
        # Return only summary
        record_api_usage(db, team_id=team_id, endpoint="recommendations_summary")
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


class ApplyRecommendationRequest(BaseModel):
    """Request body for apply/dismiss."""
    recommendation: dict = Field(
        ...,
        description="Full recommendation object (from GET /recommendations)",
    )


@router.post(
    "/apply",
    status_code=status.HTTP_200_OK,
    summary="Apply recommendation",
    description="Mark recommendation as applied. Requires team admin or API key.",
)
def apply_recommendation_action(
    payload: ApplyRecommendationRequest,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    current_user: Any = Depends(get_current_user_optional),
) -> Any:
    """
    Mark a recommendation as applied. Idempotent; safe to call multiple times.
    Viewer role cannot apply (requires owner/admin).
    """
    team_id = get_team_id_from_context(auth_ctx)
    rec = payload.recommendation
    user_id = current_user.id if current_user else None
    action, created = apply_recommendation(db, team_id, rec, status="applied", user_id=user_id)
    record_api_usage(db, team_id=team_id, endpoint="recommendations_apply")
    return {"status": "applied", "id": str(action.id), "updated": not created}


@router.post(
    "/dismiss",
    status_code=status.HTTP_200_OK,
    summary="Dismiss recommendation",
    description="Mark recommendation as dismissed. Requires team admin or API key.",
)
def dismiss_recommendation_action(
    payload: ApplyRecommendationRequest,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    current_user: Any = Depends(get_current_user_optional),
) -> Any:
    """
    Mark a recommendation as dismissed (will not act on it). Idempotent.
    """
    team_id = get_team_id_from_context(auth_ctx)
    rec = payload.recommendation
    user_id = current_user.id if current_user else None
    action, created = apply_recommendation(db, team_id, rec, status="dismissed", user_id=user_id)
    record_api_usage(db, team_id=team_id, endpoint="recommendations_dismiss")
    return {"status": "dismissed", "id": str(action.id), "updated": not created}


@router.get(
    "/actions",
    status_code=status.HTTP_200_OK,
    summary="List recommendation actions",
    description="List apply/dismiss actions for the team. Requires team access.",
)
def get_recommendation_actions(
    status_filter: str | None = Query(None, description="Filter by status: applied, dismissed"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
) -> Any:
    """List apply/dismiss history for the team."""
    team_id = get_team_id_from_context(auth_ctx)
    actions = list_actions(db, team_id, status_filter=status_filter, limit=limit)
    record_api_usage(db, team_id=team_id, endpoint="recommendations_actions")
    return [
        {
            "id": str(a.id),
            "status": a.status,
            "action_type": a.action_type,
            "estimated_savings_usd": a.estimated_savings_usd,
            "provider": a.provider,
            "gpu_type": a.gpu_type,
            "title": (a.recommendation_snapshot or {}).get("title"),
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]


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

