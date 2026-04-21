"""API endpoints for alert settings management."""

import logging
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.auth.admin_auth import require_admin
from app.models.alert_settings import AlertSettings
from app.models.team import Team
from app.schemas.alert_settings import (
    AlertSettingsCreate,
    AlertSettingsResponse,
    AlertSettingsUpdate,
)
from app.services.webhook_secrets import get_webhook_url, mask_webhook, set_webhook_url

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_response(settings: AlertSettings, db: Session) -> dict:
    """Build response dict with masked webhook (never expose full URL)."""
    data = {
        "id": settings.id,
        "team_id": settings.team_id,
        "burn_rate_threshold_usd_per_day": settings.burn_rate_threshold_usd_per_day,
        "enable_slack": settings.enable_slack,
        "enable_email": settings.enable_email,
        "email_recipients": settings.email_recipients,
        "slack_webhook_url": mask_webhook(get_webhook_url(db, settings.team_id)),
        "created_at": settings.created_at,
        "updated_at": settings.updated_at,
    }
    return data


@router.get(
    "/",
    response_model=List[AlertSettingsResponse],
    summary="List all alert settings",
    description="Retrieve alert settings for all teams (admin only)",
)
def list_alert_settings(db: Session = Depends(get_db), _: Any = Depends(require_admin)) -> Any:
    """
    List alert settings for all teams.

    Requires admin API key.
    """
    settings = db.query(AlertSettings).all()
    return [AlertSettingsResponse(**_to_response(item, db)) for item in settings]


@router.get(
    "/{team_id}",
    response_model=AlertSettingsResponse,
    summary="Get alert settings for a team",
    description="Retrieve alert settings for a specific team",
)
def get_alert_settings(team_id: UUID, db: Session = Depends(get_db), _: Any = Depends(require_admin)) -> Any:
    """
    Get alert settings for a specific team.

    If settings don't exist, returns default settings (not persisted).
    """
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()

    if not settings:
        # Return default settings without persisting
        from datetime import datetime
        from decimal import Decimal

        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Team {team_id} not found",
            )

        # Return default settings structure
        return {
            "id": "default",
            "team_id": team_id,
            "burn_rate_threshold_usd_per_day": Decimal("10000.00"),
            "enable_slack": True,
            "enable_email": False,
            "email_recipients": None,
            "slack_webhook_url": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    return AlertSettingsResponse(**_to_response(settings, db))


@router.post(
    "/",
    response_model=AlertSettingsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert settings",
    description="Create alert settings for a team (admin only)",
)
def create_alert_settings(
    settings_in: AlertSettingsCreate,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),
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
            detail=f"Team {settings_in.team_id} not found",
        )

    # Check if settings already exist
    existing = db.query(AlertSettings).filter(AlertSettings.team_id == settings_in.team_id).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Alert settings already exist for team {settings_in.team_id}",
        )

    # Create settings (exclude slack_webhook_url - handled via set_webhook_url)
    data = settings_in.model_dump(exclude={"slack_webhook_url"})
    webhook_url = settings_in.slack_webhook_url
    settings = AlertSettings(**data)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    if webhook_url:
        set_webhook_url(db, settings_in.team_id, webhook_url)
        db.refresh(settings)

    logger.info(f"Created alert settings for team {settings_in.team_id}")

    return AlertSettingsResponse(**_to_response(settings, db))


@router.put(
    "/{team_id}",
    response_model=AlertSettingsResponse,
    summary="Update alert settings",
    description="Update alert settings for a team (admin only)",
)
def update_alert_settings(
    team_id: UUID,
    settings_update: AlertSettingsUpdate,
    db: Session = Depends(get_db),
    _: Any = Depends(require_admin),
) -> Any:
    """
    Update alert settings for a team.

    Creates settings if they don't exist.
    Requires admin API key.
    """
    # Get or create settings
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()

    if not settings:
        # Check if team exists
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Team {team_id} not found",
            )

        # Create new settings with defaults
        settings = AlertSettings(team_id=team_id)
        db.add(settings)

    # Update fields (handle slack_webhook_url via set_webhook_url)
    update_data = settings_update.model_dump(exclude_unset=True)
    webhook_url = update_data.pop("slack_webhook_url", None)
    for field, value in update_data.items():
        setattr(settings, field, value)
    if webhook_url is not None:
        set_webhook_url(db, team_id, webhook_url if webhook_url else None)
    db.commit()
    db.refresh(settings)

    logger.info(f"Updated alert settings for team {team_id}")

    return AlertSettingsResponse(**_to_response(settings, db))


@router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert settings",
    description="Delete alert settings for a team (reverts to defaults)",
)
def delete_alert_settings(team_id: UUID, db: Session = Depends(get_db), _: Any = Depends(require_admin)) -> None:
    """
    Delete alert settings for a team.

    Team will revert to default settings.
    Requires admin API key.
    """
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert settings not found for team {team_id}",
        )

    db.delete(settings)
    db.commit()

    logger.info(f"Deleted alert settings for team {team_id}")
