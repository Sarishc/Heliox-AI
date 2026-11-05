"""Auth0 sign-in routes. See app/auth/auth0.py for the flow."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.routes.auth import _set_auth_cookie
from app.auth import auth0
from app.auth.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/config", summary="Which sign-in methods are available")
def auth_config() -> dict:
    """Public: lets the login page show Auth0 or the legacy forms, and log out of Auth0."""
    enabled = auth0.is_enabled()
    return {
        "auth0_enabled": enabled,
        "legacy_auth_enabled": get_settings().LEGACY_AUTH_ENABLED,
        "logout_url": auth0.logout_url() if enabled else None,
    }


@router.get("/auth0/login", summary="Start Auth0 sign-in (redirects to Auth0)")
def auth0_login(
    redirect: Optional[str] = Query(None, description="Path to return to after sign-in, e.g. /analytics"),
    signup: bool = Query(False, description="Open Auth0's sign-up screen instead of log-in"),
) -> RedirectResponse:
    if not auth0.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth0 is not configured. Set AUTH0_DOMAIN, AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET.",
        )
    authorize_url, binding = auth0.start_login(redirect, signup=signup)
    response = RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=auth0.TX_COOKIE_NAME,
        value=binding,
        max_age=auth0.STATE_TTL_SECONDS,
        path=auth0.TX_COOKIE_PATH,
        httponly=True,
        secure=auth0.tx_cookie_secure(),
        samesite="lax",
    )
    return response


@router.get("/auth0/callback", summary="Auth0 redirects here after sign-in")
def auth0_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    frontend = get_settings().FRONTEND_URL.rstrip("/")

    def finish(target: str) -> RedirectResponse:
        response = RedirectResponse(f"{frontend}{target}", status_code=status.HTTP_302_FOUND)
        response.delete_cookie(
            key=auth0.TX_COOKIE_NAME,
            path=auth0.TX_COOKIE_PATH,
            httponly=True,
            secure=auth0.tx_cookie_secure(),
            samesite="lax",
        )
        return response

    def back_to_login(reason: str) -> RedirectResponse:
        return finish(f"/login?error={reason}")

    login_state = auth0.pop_state(state, request.cookies.get(auth0.TX_COOKIE_NAME)) if state else None
    if error:
        logger.info("Auth0 sign-in not completed")
        return back_to_login("auth0_denied")
    if not code or not login_state:
        return back_to_login("auth0_state")

    try:
        tokens = auth0.exchange_code(code, login_state["code_verifier"])
        claims = auth0.verify_id_token(tokens.get("id_token", ""), login_state["nonce"])
        user, created_team = auth0.sign_in_user(db, claims)
    except auth0.Auth0Error as exc:
        db.rollback()
        logger.warning("Auth0 sign-in failed (%s): %s", exc.code, exc)
        return back_to_login(exc.code)

    # New teams go through onboarding; returning users go back where they started
    target = "/onboarding" if created_team else (login_state.get("redirect") or "/")
    response = finish(target)
    session_token = create_access_token(
        data={"sub": user.email}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    _set_auth_cookie(response, session_token)
    logger.info("Auth0 sign-in for user %s (new team: %s)", user.id, created_team)
    return response
