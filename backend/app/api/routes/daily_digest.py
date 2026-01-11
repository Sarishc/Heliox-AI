"""API endpoints for daily digest generation."""
import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_api_key
from app.schemas.alert_settings import DailyDigestPayload
from app.services.daily_digest import DailyDigestGenerator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=DailyDigestPayload,
    summary="Generate daily digest",
    description="Generate daily digest with cost data and recommendations for all teams"
)
def generate_daily_digest(
    target_date: str = Query(
        default=None,
        description="Date for digest (YYYY-MM-DD). Defaults to yesterday.",
        example="2026-01-09"
    ),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
) -> Any:
    """
    Generate daily digest payload.
    
    Returns comprehensive cost and recommendation data for all teams.
    Requires admin API key.
    
    **Use Cases:**
    - Generate email/Slack digests
    - Executive reporting
    - Cost review meetings
    - Team performance tracking
    
    **Contains:**
    - Global cost summary (daily, weekly, monthly)
    - Per-team cost breakdowns
    - Top GPU consuming models (global + per team)
    - Top cost optimization recommendations
    - Potential savings calculations
    """
    # Parse date
    if target_date:
        try:
            date_obj = date.fromisoformat(target_date)
        except ValueError:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date format: {target_date}. Use YYYY-MM-DD."
            )
    else:
        date_obj = date.today() - timedelta(days=1)
    
    # Generate digest
    generator = DailyDigestGenerator(db)
    digest = generator.generate_daily_digest(date_obj)
    
    logger.info(f"Generated daily digest for {digest.date}")
    
    return digest

