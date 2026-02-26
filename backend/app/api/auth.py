"""Authentication endpoints with httpOnly cookie support."""
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from app.auth.cookie_auth import get_token_from_cookie_or_header, blacklist_token, is_token_blacklisted
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.auth.brute_force import (
    check_login_rate_limit,
    record_login_attempt,
    is_locked_out,
    is_captcha_required,
    clear_captcha_requirement,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.crud import user as crud_user
from app.schemas.user import User, UserCreate, Token

router = APIRouter()
settings = get_settings()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"




def _set_auth_cookie(response: Response, token: str) -> None:
    """Set httpOnly, Secure, SameSite=Strict auth cookie."""
    secure = settings.ENV in ("production", "staging")
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie."""
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
    )


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate
) -> Any:
    """
    Register a new user.
    Auto-creates a default team and adds the user as owner so they can use the dashboard.
    """
    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    user = crud_user.create(db, obj_in=user_in)
    # Create default team and add user as owner (required for dashboard access)
    base = (user_in.full_name or user_in.email.split("@")[0]).strip() or "My"
    team_name = f"{base}'s Team"
    existing = db.query(Team).filter(Team.name == team_name).first()
    if existing:
        team_name = f"{team_name} ({user_in.email.split('@')[0]})"
    team = Team(name=team_name)
    db.add(team)
    db.flush()
    membership = TeamMember(
        team_id=team.id,
        user_id=user.id,
        role=TeamRole.OWNER,
    )
    db.add(membership)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login")
def login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    Login with email/password. OWASP: rate limit 5/min, lockout after 5 failures,
    CAPTCHA after 3 failures. Sets httpOnly cookie with JWT.
    """
    client_ip = _get_client_ip(request)

    # Rate limit: 5 login attempts per minute per IP
    limited, retry_after = check_login_rate_limit(client_ip)
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # Account lockout after 5 failed attempts
    locked, remaining = is_locked_out(client_ip)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked. Try again in {remaining} seconds.",
            headers={"Retry-After": str(remaining)},
        )

    # CAPTCHA required after 3 failures
    captcha_needed = is_captcha_required(client_ip)
    captcha_token = request.headers.get("X-Captcha-Token")
    if captcha_needed:
        if not captcha_token or not clear_captcha_requirement(client_ip, captcha_token):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CAPTCHA required. Please complete the CAPTCHA and resubmit.",
            )

    user = crud_user.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        locked_out, captcha_required, lockout_sec = record_login_attempt(
            client_ip, form_data.username, success=False
        )
        if locked_out:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts. Account locked for {lockout_sec // 60} minutes.",
                headers={"Retry-After": str(lockout_sec)},
            )
        detail = {"message": "Incorrect email or password"}
        if captcha_required:
            detail["captcha_required"] = True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )
    if not crud_user.is_active(user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    record_login_attempt(client_ip, form_data.username, success=True)

    # Ensure user has a team (fixes users who registered before auto-team was added)
    membership = db.query(TeamMember).filter(TeamMember.user_id == user.id).first()
    if not membership:
        base = (user.full_name or user.email.split("@")[0] or "My").strip()
        team_name = f"{base}'s Team"
        if db.query(Team).filter(Team.name == team_name).first():
            team_name = f"{team_name} ({user.email.split('@')[0]})"
        team = Team(name=team_name)
        db.add(team)
        db.flush()
        db.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
        db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    _set_auth_cookie(response, access_token)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        },
        "message": "Login successful",
    }


class SetSessionRequest(BaseModel):
    """Request body for set-session endpoint."""
    token: str
    redirect: str = "/"


@router.post("/set-session")
def set_session(
    body: SetSessionRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> Any:
    """
    Exchange one-time token (e.g. from OAuth callback) for httpOnly session cookie.
    Validates token, sets secure cookie, returns redirect URL.
    Used by frontend after OAuth to establish session without storing token in JS.
    """
    from jose import jwt, JWTError
    from uuid import UUID
    from app.auth.security import SECRET_KEY, ALGORITHM

    try:
        payload = jwt.decode(
            body.token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = None
    if email:
        user = crud_user.get_by_email(db, email=email)
    if not user and sub:
        try:
            uid = UUID(str(sub))
            user = crud_user.get(db, id=uid)
        except (ValueError, TypeError):
            user = crud_user.get_by_email(db, email=str(sub))

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not crud_user.is_active(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    session_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    _set_auth_cookie(response, session_token)
    return {"redirect": body.redirect or "/", "message": "Session established"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
) -> Any:
    """
    Logout: blacklist current token and clear auth cookie.
    """
    token = get_token_from_cookie_or_header(request)
    if token:
        blacklist_token(token)
    _clear_auth_cookie(response)
    return {"message": "Logged out successfully"}

