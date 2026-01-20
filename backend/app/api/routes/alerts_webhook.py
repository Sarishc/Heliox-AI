"""Team-scoped Slack webhook management."""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.core.tenant import require_team_access
from app.models.alert_settings import AlertSettings
from app.models.team_member import TeamRole
from app.schemas.alert_settings import SlackWebhookRequest, SlackWebhookResponse

router = APIRouter()


def _mask_webhook(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return f"***{url[-8:]}"


@router.post("/webhook", response_model=SlackWebhookResponse, status_code=status.HTTP_201_CREATED)
def set_slack_webhook(
    payload: SlackWebhookRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Any:
    team_id = payload.team_id
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    settings = (
        db.query(AlertSettings)
        .filter(AlertSettings.team_id == team_id)
        .first()
    )
    if not settings:
        settings = AlertSettings(team_id=payload.team_id)
        db.add(settings)
    settings.slack_webhook_url = payload.slack_webhook_url
    settings.enable_slack = True
    db.commit()
    return SlackWebhookResponse(
        team_id=team_id,
        configured=True,
        masked_webhook_url=_mask_webhook(payload.slack_webhook_url),
    )


@router.get("/webhook", response_model=SlackWebhookResponse)
def get_slack_webhook(
    team_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Any:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    settings = (
        db.query(AlertSettings)
        .filter(AlertSettings.team_id == team_id)
        .first()
    )
    return SlackWebhookResponse(
        team_id=team_id,
        configured=bool(settings and settings.slack_webhook_url),
        masked_webhook_url=_mask_webhook(settings.slack_webhook_url if settings else None),
    )


@router.delete("/webhook", status_code=status.HTTP_204_NO_CONTENT)
def delete_slack_webhook(
    team_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> None:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    settings = (
        db.query(AlertSettings)
        .filter(AlertSettings.team_id == team_id)
        .first()
    )
    if settings:
        settings.slack_webhook_url = None
        settings.enable_slack = False
        db.commit()
