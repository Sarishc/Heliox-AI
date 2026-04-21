"""Authentication dependencies for FastAPI."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.auth.security import SECRET_KEY
from app.auth.cookie_auth import get_token_from_cookie_or_header, is_token_blacklisted
from app.core.db import get_db
from app.crud import user as crud_user
from app.models.user import User
from app.schemas.user import TokenData

# OAuth2 scheme for token authentication (Authorization: Bearer header) - optional for cookie fallback
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


async def get_token_required(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """Get token from cookie or header. Raises 401 if missing."""
    token = get_token_from_cookie_or_header(request) or header_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(get_token_required),
) -> User:
    """
    Get current authenticated user from JWT token (cookie or Authorization header).

    Args:
        request: FastAPI request (for cookie extraction)
        db: Database session
        token: JWT token from Authorization header (optional)

    Returns:
        User instance

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # OWASP: Strict JWT - HS256 only, require exp
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        email: Optional[str] = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception

    user = crud_user.get_by_email(db, email=token_data.email)
    if user is None:
        raise credentials_exception

    return user


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme_optional),
) -> Optional[User]:
    """
    Get current user if token is provided (cookie or header), otherwise return None.
    """
    resolved_token = get_token_from_cookie_or_header(request) or token
    if not resolved_token or is_token_blacklisted(resolved_token):
        return None
    try:
        payload = jwt.decode(
            resolved_token,
            SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        email: Optional[str] = payload.get("sub")
        if email is None:
            return None
        token_data = TokenData(email=email)
    except JWTError:
        return None

    user = crud_user.get_by_email(db, email=token_data.email)
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get current active user.

    Args:
        current_user: Current authenticated user

    Returns:
        User instance

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user
