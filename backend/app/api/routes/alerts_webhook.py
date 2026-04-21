"""Team-scoped Slack webhook and email alert management."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.core.tenant import require_team_access
from app.models.alert_settings import AlertSettings
from app.models.team_member import TeamRole
from app.schemas.alert_settings import (
    EmailAlertsRequest,
    EmailAlertsResponse,
    SlackWebhookRequest,
    SlackWebhookResponse,
    _mask_email_recipients,
)
from app.services.webhook_secrets import get_webhook_url, mask_webhook, set_webhook_url

router = APIRouter()


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
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()
    set_webhook_url(db, team_id, payload.slack_webhook_url)
    return SlackWebhookResponse(
        team_id=team_id,
        configured=True,
        masked_webhook_url=mask_webhook(payload.slack_webhook_url),
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
    webhook_url = get_webhook_url(db, team_id)
    return SlackWebhookResponse(
        team_id=team_id,
        configured=bool(webhook_url),
        masked_webhook_url=mask_webhook(webhook_url),
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
    set_webhook_url(db, team_id, None)


# --- Email alerts ---


@router.get("/email", response_model=EmailAlertsResponse)
def get_email_alerts(
    team_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Any:
    """Get email alert settings for the team (owner/admin only)."""
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()
    if not settings:
        return EmailAlertsResponse(
            team_id=team_id,
            enabled=False,
            recipient_count=0,
            masked_recipients=None,
        )
    count, masked = _mask_email_recipients(settings.email_recipients)
    return EmailAlertsResponse(
        team_id=team_id,
        enabled=bool(settings.enable_email and settings.email_recipients),
        recipient_count=count,
        masked_recipients=masked,
    )


@router.post("/email", response_model=EmailAlertsResponse, status_code=status.HTTP_201_CREATED)
def set_email_alerts(
    payload: EmailAlertsRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Any:
    """Enable email alerts and set recipients (owner/admin only)."""
    require_team_access(
        db,
        user=current_user,
        team_id=payload.team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == payload.team_id).first()
    if not settings:
        settings = AlertSettings(team_id=payload.team_id)
        db.add(settings)
    settings.enable_email = payload.enable_email
    # Normalize: comma-separated, dedupe, trim
    recipients = [e.strip().lower() for e in payload.email_recipients.split(",") if e.strip() and "@" in e]
    seen = set()
    unique = []
    for e in recipients:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    settings.email_recipients = ", ".join(unique) if unique else None
    if not settings.email_recipients:
        settings.enable_email = False
    db.commit()
    db.refresh(settings)
    count, masked = _mask_email_recipients(settings.email_recipients)
    return EmailAlertsResponse(
        team_id=payload.team_id,
        enabled=bool(settings.enable_email),
        recipient_count=count,
        masked_recipients=masked,
    )


@router.delete("/email", status_code=status.HTTP_204_NO_CONTENT)
def delete_email_alerts(
    team_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> None:
    """Disable email alerts for the team (owner/admin only)."""
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()
    if settings:
        settings.enable_email = False
        settings.email_recipients = None
        db.commit()
