"""API routes for billing and usage metering."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.db import get_db
from app.models.team_api_key import TeamAPIKey
from app.models.usage import UsageDailyRollup, UsageEvent, UsageEventType

router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic schemas
class UsageBreakdown(BaseModel):
    """Usage breakdown by event type."""
    event_type: str = Field(description="Type of usage event")
    total_quantity: int = Field(description="Total quantity for the period")
    unit: str = Field(description="Unit of measurement (requests, line_items, seats, nodes)")


class UsageDailySummary(BaseModel):
    """Daily usage summary."""
    usage_date: date = Field(description="Date of the usage", alias="date")
    api_requests: int = Field(default=0, description="Number of API requests")
    ingestion_line_items: int = Field(default=0, description="Number of ingested line items")
    seats: int = Field(default=0, description="Number of active seats")
    gpu_nodes: int = Field(default=0, description="Number of monitored GPU nodes")
    
    class Config:
        populate_by_name = True


class UsageSummaryResponse(BaseModel):
    """Usage summary response."""
    team_id: str = Field(description="Team ID")
    start_date: date = Field(description="Start date of the period")
    end_date: date = Field(description="End date of the period")
    breakdown: List[UsageBreakdown] = Field(description="Usage breakdown by type")
    daily_summary: List[UsageDailySummary] = Field(description="Daily usage data")
    totals: Dict[str, int] = Field(description="Total usage for the period")


@router.get("/usage", response_model=UsageSummaryResponse, summary="Get usage summary for a date range")
def get_usage_summary(
    *,
    db: Session = Depends(get_db),
    auth: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
    from_date: Optional[date] = Query(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, alias="to", description="End date (YYYY-MM-DD)")
):
    """
    Get usage summary for a team.
    
    Returns aggregated usage data for billing purposes.
    Defaults to last 30 days if no dates provided.
    
    Query Parameters:
    - from: Start date (default: 30 days ago)
    - to: End date (default: today)
    
    Returns:
    - Usage breakdown by event type
    - Daily usage summary
    - Total usage for the period
    """
    # Default date range: last 30 days
    if not to_date:
        to_date = datetime.utcnow().date()
    if not from_date:
        from_date = to_date - timedelta(days=30)
    
    # Validate date range
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be before end date"
        )
    
    # Limit date range to prevent excessive queries
    if (to_date - from_date).days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 365 days"
        )
    
    team_id = auth.team_id
    logger.info(f"Fetching usage for team {team_id} from {from_date} to {to_date}")

    # Query aggregated usage from daily rollups
    rollup_query = db.query(
        UsageDailyRollup.event_type,
        func.sum(UsageDailyRollup.total_quantity).label('total_quantity')
    ).filter(
        UsageDailyRollup.team_id == team_id,
        UsageDailyRollup.date >= from_date,
        UsageDailyRollup.date <= to_date
    ).group_by(
        UsageDailyRollup.event_type
    ).all()
    
    # Build breakdown
    breakdown = []
    totals = {
        "api_requests": 0,
        "ingestion_line_items": 0,
        "seats": 0,
        "gpu_nodes": 0
    }
    
    unit_map = {
        UsageEventType.API_REQUEST: "requests",
        UsageEventType.INGESTION: "line_items",
        UsageEventType.SEAT: "seats",
        UsageEventType.GPU_NODE: "nodes"
    }
    
    for row in rollup_query:
        event_type_str = row.event_type.value if isinstance(row.event_type, UsageEventType) else row.event_type
        total_quantity = int(row.total_quantity) if row.total_quantity else 0
        
        breakdown.append(UsageBreakdown(
            event_type=event_type_str,
            total_quantity=total_quantity,
            unit=unit_map.get(row.event_type, "units")
        ))
        
        # Update totals
        if event_type_str == "api_request":
            totals["api_requests"] = total_quantity
        elif event_type_str == "ingestion":
            totals["ingestion_line_items"] = total_quantity
        elif event_type_str == "seat":
            totals["seats"] = total_quantity
        elif event_type_str == "gpu_node":
            totals["gpu_nodes"] = total_quantity
    
    # Query daily summary
    daily_query = db.query(
        UsageDailyRollup.date,
        UsageDailyRollup.event_type,
        UsageDailyRollup.total_quantity
    ).filter(
        UsageDailyRollup.team_id == team_id,
        UsageDailyRollup.date >= from_date,
        UsageDailyRollup.date <= to_date
    ).order_by(
        UsageDailyRollup.date.desc()
    ).all()
    
    # Group daily data by date
    daily_data: Dict[date, Dict[str, int]] = {}
    for row in daily_query:
        row_date = row.date
        event_type_str = row.event_type.value if isinstance(row.event_type, UsageEventType) else row.event_type
        total_quantity = int(row.total_quantity) if row.total_quantity else 0
        
        if row_date not in daily_data:
            daily_data[row_date] = {
                "api_requests": 0,
                "ingestion_line_items": 0,
                "seats": 0,
                "gpu_nodes": 0
            }
        
        if event_type_str == "api_request":
            daily_data[row_date]["api_requests"] = total_quantity
        elif event_type_str == "ingestion":
            daily_data[row_date]["ingestion_line_items"] = total_quantity
        elif event_type_str == "seat":
            daily_data[row_date]["seats"] = total_quantity
        elif event_type_str == "gpu_node":
            daily_data[row_date]["gpu_nodes"] = total_quantity
    
    # Convert to list of UsageDailySummary
    daily_summary = [
        UsageDailySummary(
            date=d,
            api_requests=data["api_requests"],
            ingestion_line_items=data["ingestion_line_items"],
            seats=data["seats"],
            gpu_nodes=data["gpu_nodes"]
        )
        for d, data in sorted(daily_data.items(), reverse=True)
    ]
    
    return UsageSummaryResponse(
        team_id=str(team_id),
        start_date=from_date,
        end_date=to_date,
        breakdown=breakdown,
        daily_summary=daily_summary,
        totals=totals
    )


@router.get("/usage/current-month", response_model=UsageSummaryResponse, summary="Get current month usage summary")
def get_current_month_usage(
    *,
    db: Session = Depends(get_db),
    auth: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session)
):
    """
    Get usage summary for the current month.

    Convenience endpoint for fetching current billing period usage.
    """
    # Calculate current month date range
    today = datetime.utcnow().date()
    first_day_of_month = date(today.year, today.month, 1)

    return get_usage_summary(
        db=db,
        auth=auth,
        from_date=first_day_of_month,
        to_date=today
    )


@router.get("/usage/events/recent", summary="Get recent billing usage events")
def get_recent_usage_events(
    *,
    db: Session = Depends(get_db),
    auth: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
    limit: int = Query(100, le=1000, description="Number of events to return"),
    event_type: Optional[UsageEventType] = Query(None, description="Filter by event type")
):
    """
    Get recent usage events for debugging purposes.
    
    Returns raw usage events (not rollups).
    Limited to last 30 days based on retention policy.
    """
    query = db.query(UsageEvent).filter(
        UsageEvent.team_id == auth.team_id
    )
    
    if event_type:
        query = query.filter(UsageEvent.event_type == event_type)
    
    # Order by most recent and limit
    events = query.order_by(
        UsageEvent.created_at.desc()
    ).limit(limit).all()
    
    return {
        "team_id": str(auth.team_id),
        "count": len(events),
        "events": [
            {
                "id": str(event.id),
                "event_type": event.event_type.value,
                "quantity": event.quantity,
                "metadata": event.event_metadata,
                "created_at": event.created_at.isoformat()
            }
            for event in events
        ]
    }
