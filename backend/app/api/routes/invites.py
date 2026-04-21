"""Team invite endpoints: validate token and accept invite."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user_optional
from app.auth.security import create_access_token
from app.core.audit import record_audit_event
from app.core.config import get_settings
from app.core.db import get_db
from app.crud import team_member as crud_team_member
from app.crud import user as crud_user
from app.models.team import Team
from app.models.team_invite import TeamInvite, hash_invite_token
from app.models.team_member import TeamMember, TeamRole
from app.schemas.team_invite import InviteAcceptBody, InviteValidateResponse
from app.schemas.user import UserCreate

router = APIRouter()
settings = get_settings()


def _get_invite_by_token(db: Session, token: str) -> TeamInvite | None:
    token_hash = hash_invite_token(token)
    return db.query(TeamInvite).filter(TeamInvite.token_hash == token_hash).first()


def _invite_valid(invite: TeamInvite) -> bool:
    if invite.accepted_at:
        return False
    if invite.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        return False
    return True


@router.get("/{token}", response_model=InviteValidateResponse, tags=["Invites"])
def validate_invite(
    token: str,
    db: Session = Depends(get_db),
) -> InviteValidateResponse:
    """
    Validate an invite token. Public endpoint - no auth required.
    Returns invite details for display on accept page.
    """
    invite = _get_invite_by_token(db, token)
    if not invite or not _invite_valid(invite):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or expired",
        )
    team = db.query(Team).filter(Team.id == invite.team_id).first()
    team_name = team.name if team else "Unknown"
    inviter_name = None
    if invite.invited_by_user_id:
        inviter = crud_user.get(db, invite.invited_by_user_id)
        inviter_name = (inviter.full_name or inviter.email) if inviter else None
    return InviteValidateResponse(
        valid=True,
        team_name=team_name,
        team_id=invite.team_id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        inviter_name=inviter_name,
    )


@router.post("/{token}/accept", tags=["Invites"])
def accept_invite(
    token: str,
    body: InviteAcceptBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
) -> dict:
    """
    Accept a team invite.
    - If logged in and email matches: add membership.
    - If not logged in and user exists: must log in first (return 400).
    - If not logged in and user is new: create user and add membership.
    """
    invite = _get_invite_by_token(db, token)
    if not invite or not _invite_valid(invite):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found or expired",
        )
    if body.email.lower() != invite.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email does not match invite",
        )

    user = crud_user.get_by_email(db, email=body.email)

    if current_user:
        if current_user.email.lower() != body.email.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Logged-in user email does not match invite. Please log out and use the invite email.",
            )
        user = current_user
    else:
        if user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists. Please log in first, then accept the invite.",
            )
        if not body.password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password required to create account",
            )
        user = crud_user.create(
            db,
            obj_in=UserCreate(
                email=body.email,
                password=body.password,
                full_name=body.full_name or body.email.split("@")[0],
            ),
        )
        access_token = create_access_token(data={"sub": str(user.email)})
        secure = settings.ENV in ("production", "staging")
        response.set_cookie(
            key=settings.AUTH_COOKIE_NAME,
            value=access_token,
            max_age=settings.AUTH_COOKIE_MAX_AGE,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )

    existing = crud_team_member.get_by_team_and_user(db, team_id=invite.team_id, user_id=user.id)
    if existing:
        invite.accepted_at = datetime.now(timezone.utc)
        invite.accepted_by_user_id = user.id
        db.commit()
        return {
            "message": "You are already a member of this team",
            "team_id": str(invite.team_id),
        }

    membership = TeamMember(
        team_id=invite.team_id,
        user_id=user.id,
        role=TeamRole(invite.role),
    )
    db.add(membership)
    invite.accepted_at = datetime.now(timezone.utc)
    invite.accepted_by_user_id = user.id
    db.commit()

    record_audit_event(
        db,
        team_id=invite.team_id,
        actor_type="user",
        actor_id=str(user.id),
        action="invite_accepted",
        metadata={
            "invite_id": str(invite.id),
            "member_user_id": str(user.id),
            "role": invite.role,
        },
    )

    return {
        "message": "Invite accepted",
        "team_id": str(invite.team_id),
    }
