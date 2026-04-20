"""Authentication endpoints with httpOnly cookie support."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
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

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"




def _set_auth_cookie(response: Response, token: str) -> None:
    """Set httpOnly auth cookie. Use strict samesite (proxy makes requests same-origin)."""
    secure = settings.ENV in ("production", "staging")
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",  # Lax allows cookie on top-level nav; works with proxy
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie."""
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Register a new user account")
def register(
    *,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks,
    user_in: UserCreate,
) -> Any:
    """
    Register a new user.
    Auto-creates a default team and adds the user as owner so they can use the dashboard.
    Sends an email verification link in the background when email is configured.
    Returns email_configured=false in response when RESEND_API_KEY is not set so the
    frontend can display an inline notice to the user.
    """
    from app.services.email_notifications import send_email_verification, is_email_configured

    existing_user = crud_user.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    user = crud_user.create(db, obj_in=user_in)
    # Create default team and add user as owner (required for dashboard access)
    base = (user_in.full_name or user_in.email.split("@")[0]).strip() or "My"
    team_name = f"{base}'s Team"
    existing_team = db.query(Team).filter(Team.name == team_name).first()
    if existing_team:
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

    # Generate email verification token
    raw_token = crud_user.create_email_verification_token(db, user=user)
    db.commit()
    db.refresh(user)

    email_configured = is_email_configured()

    if email_configured:
        # Send verification email asynchronously (non-blocking)
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        verify_url = f"{frontend_url}/verify-email?token={raw_token}"
        background_tasks.add_task(
            asyncio.run,
            send_email_verification(to_email=user.email, verify_url=verify_url),
        )
        logger.info(f"Registered user {user.id}, verification email queued")
    else:
        logger.warning(
            f"Registered user {user.id} but RESEND_API_KEY is not configured; "
            "verification email was NOT sent"
        )

    # Return user dict with extra email_configured flag so frontend can show notice
    user_dict = {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "email_configured": email_configured,
    }
    return user_dict


@router.post("/login", summary="Authenticate and receive session cookie")
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


@router.post("/set-session", summary="Set session from OAuth token")
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


@router.post("/logout", summary="Invalidate session and clear auth cookie")
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


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, summary="Request password reset email")
def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Any:
    """
    Request a password reset email.
    Always returns 202 regardless of whether the email exists (prevents enumeration).
    Returns 503 if email delivery is not configured — the user must know so they
    can contact support rather than waiting for an email that will never arrive.
    """
    from app.services.email_notifications import send_password_reset_email, is_email_configured

    if not is_email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email delivery is not configured. "
                "Contact support to reset your password."
            ),
        )

    user = crud_user.get_by_email(db, email=body.email)
    if user and user.is_active:
        raw_token = crud_user.create_password_reset_token(db, user=user)
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        reset_url = f"{frontend_url}/reset-password?token={raw_token}"
        background_tasks.add_task(
            asyncio.run,
            send_password_reset_email(
                to_email=user.email,
                reset_url=reset_url,
                expires_minutes=60,
            ),
        )
        logger.info(f"Password reset email queued for user {user.id}")
    else:
        # Constant-time response to prevent email enumeration
        logger.info(f"Password reset requested for unknown/inactive email: {body.email}")

    return {"message": "If that email is registered you will receive a reset link shortly"}


@router.post("/reset-password", summary="Reset password using email token")
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Consume a password reset token and set a new password.
    Token is single-use and expires after 60 minutes.
    """
    user = crud_user.get_by_password_reset_token(db, raw_token=body.token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # Check expiry
    expires_at = user.password_reset_token_expires_at
    if expires_at is None or datetime.now(timezone.utc) > expires_at:
        # Wipe the stale token
        user.password_reset_token = None
        user.password_reset_token_expires_at = None
        db.add(user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one.",
        )

    crud_user.reset_password(db, user=user, new_password=body.new_password)
    logger.info(f"Password reset completed for user {user.id}")
    return {"message": "Password updated successfully. Please log in with your new password."}


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class ResendVerificationRequest(BaseModel):
    email: EmailStr


@router.get("/verify-email", summary="Verify email address from link")
def verify_email(
    token: str,
    db: Session = Depends(get_db),
) -> Any:
    """
    Verify a user's email address using the token from the verification email.
    Safe to call multiple times (idempotent if already verified).
    """
    user = crud_user.get_by_email_verification_token(db, raw_token=token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or already-used verification token",
        )
    crud_user.mark_email_verified(db, user=user)
    logger.info(f"Email verified for user {user.id}")
    return {"message": "Email verified successfully. You can now log in."}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED, summary="Resend email verification link")
def resend_verification(
    body: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Any:
    """
    Re-send the email verification link.
    Returns 503 if email delivery is not configured — otherwise returns 202 to
    prevent email enumeration.
    """
    from app.services.email_notifications import send_email_verification, is_email_configured

    if not is_email_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Email delivery is not configured. "
                "Contact support to verify your email address."
            ),
        )

    user = crud_user.get_by_email(db, email=body.email)
    if user and user.is_active and not user.email_verified:
        raw_token = crud_user.create_email_verification_token(db, user=user)
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        verify_url = f"{frontend_url}/verify-email?token={raw_token}"
        background_tasks.add_task(
            asyncio.run,
            send_email_verification(to_email=user.email, verify_url=verify_url),
        )
        logger.info(f"Verification email re-queued for user {user.id}")

    return {"message": "If that address is registered and unverified, a new link has been sent"}

