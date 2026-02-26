"""Platform admin authorization (replaces global admin API key)."""
from fastapi import Depends, HTTPException, status

from app.auth.deps import get_current_active_user
from app.models.user import User


def require_platform_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Require the current user to be a platform admin.
    Replaces verify_admin_api_key for RBAC-based admin access.
    """
    if not getattr(current_user, "is_platform_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )
    return current_user
