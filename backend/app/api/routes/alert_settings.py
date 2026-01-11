"""API endpoints for alert settings management."""
import logging
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_api_key
from app.models.alert_settings import AlertSettings
from app.models.team import Team
from app.schemas.alert_settings import (
    AlertSettingsCreate,
    AlertSettingsResponse,
    AlertSettingsUpdate
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/",
    response_model=List[AlertSettingsResponse],
    summary="List all alert settings",
    description="Retrieve alert settings for all teams (admin only)"
)
def list_alert_settings(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
) -> Any:
    """
    List alert settings for all teams.
    
    Requires admin API key.
    """
    settings = db.query(AlertSettings).all()
    return settings


@router.get(
    "/{team_id}",
    response_model=AlertSettingsResponse,
    summary="Get alert settings for a team",
    description="Retrieve alert settings for a specific team"
)
def get_alert_settings(
    team_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
) -> Any:
    """
    Get alert settings for a specific team.
    
    If settings don't exist, returns default settings (not persisted).
    """
    settings = db.query(AlertSettings).filter(
        AlertSettings.team_id == team_id
    ).first()
    
    if not settings:
        # Return default settings without persisting
        from datetime import datetime
        from decimal import Decimal
        
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Team {team_id} not found"
            )
        
        # Return default settings structure
        return {
            "id": "default",
            "team_id": team_id,
            "burn_rate_threshold_usd_per_day": Decimal("10000.00"),
            "enable_slack": True,
            "enable_email": False,
            "email_recipients": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    
    return settings


@router.post(
    "/",
    response_model=AlertSettingsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert settings",
    description="Create alert settings for a team (admin only)"
)
def create_alert_settings(
    settings_in: AlertSettingsCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
) -> Any:
    """
    Create alert settings for a team.
    
    Requires admin API key.
    """
    # Check if team exists
    team = db.query(Team).filter(Team.id == settings_in.team_id).first()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {settings_in.team_id} not found"
        )
    
    # Check if settings already exist
    existing = db.query(AlertSettings).filter(
        AlertSettings.team_id == settings_in.team_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alert settings already exist for team {settings_in.team_id}"
        )
    
    # Create settings
    settings = AlertSettings(**settings_in.model_dump())
    db.add(settings)
    db.commit()
    db.refresh(settings)
    
    logger.info(f"Created alert settings for team {settings_in.team_id}")
    
    return settings


@router.put(
    "/{team_id}",
    response_model=AlertSettingsResponse,
    summary="Update alert settings",
    description="Update alert settings for a team (admin only)"
)
def update_alert_settings(
    team_id: str,
    settings_update: AlertSettingsUpdate,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
) -> Any:
    """
    Update alert settings for a team.
    
    Creates settings if they don't exist.
    Requires admin API key.
    """
    # Get or create settings
    settings = db.query(AlertSettings).filter(
        AlertSettings.team_id == team_id
    ).first()
    
    if not settings:
        # Check if team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Team {team_id} not found"
            )
        
        # Create new settings with defaults
        settings = AlertSettings(team_id=team_id)
        db.add(settings)
    
    # Update fields
    update_data = settings_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    
    db.commit()
    db.refresh(settings)
    
    logger.info(f"Updated alert settings for team {team_id}")
    
    return settings


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert settings",
    description="Delete alert settings for a team (reverts to defaults)"
)
def delete_alert_settings(
    team_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
) -> None:
    """
    Delete alert settings for a team.
    
    Team will revert to default settings.
    Requires admin API key.
    """
    settings = db.query(AlertSettings).filter(
        AlertSettings.team_id == team_id
    ).first()
    
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert settings not found for team {team_id}"
        )
    
    db.delete(settings)
    db.commit()
    
    logger.info(f"Deleted alert settings for team {team_id}")

