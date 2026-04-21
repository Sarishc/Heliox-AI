"""
Admin authorization: RBAC (platform admin) or legacy API key.

Replaces global admin god-mode with role-based access.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status

from app.auth.deps import get_current_user_optional
from app.core.config import get_settings
from app.models.user import User

settings = get_settings()


async def require_admin(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> User | str:
    """
    Require admin access via:
    1) Platform admin (session) - user with is_platform_admin=True
    2) Legacy ADMIN_API_KEY (when configured) - for scripts/CI

    Returns User if session-based, or "api_key" if key-based.
    """
    # 1. Try platform admin (RBAC)
    if current_user and getattr(current_user, "is_platform_admin", False):
        return current_user

    # 2. Try legacy admin API key (deprecated)
    if settings.ADMIN_API_KEY and x_api_key:
        import secrets

        if secrets.compare_digest(x_api_key, settings.ADMIN_API_KEY):
            return "api_key"

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required (platform admin or valid admin API key)",
    )
