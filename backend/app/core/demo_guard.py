"""Demo mode protection.

When DEMO_MODE=True, write operations (POST/PUT/PATCH/DELETE) on the demo
tenant are blocked with a structured 403 that prompts signup.

Usage in routes:
    from app.core.demo_guard import require_not_demo
    require_not_demo(db, auth_ctx.team_id)

Usage as middleware (automatic for all routes):
    app.add_middleware(DemoModeMiddleware)
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# HTTP methods that mutate state
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths that are always allowed even in demo mode (seed/reset by admin)
_DEMO_ADMIN_PATHS = frozenset({
    "/api/v1/admin/demo/seed",
    "/api/v1/admin/demo/reset",
})


def _demo_403_body(signup_url: str) -> dict:
    return {
        "error": "demo_mode",
        "message": (
            "This action is disabled in the demo environment. "
            "Sign up for a free account to get started."
        ),
        "signup_url": signup_url,
    }


def require_not_demo(team_id: UUID | str | None) -> None:
    """Raise HTTP 403 if the acting team is the demo tenant.

    Call this at the top of any route handler that performs a write before
    doing any DB work.  Does nothing when DEMO_MODE is off or DEMO_TENANT_ID
    is not configured.
    """
    settings = get_settings()
    if not settings.DEMO_MODE or not settings.DEMO_TENANT_ID:
        return
    if team_id is None:
        return
    try:
        if str(team_id) == settings.DEMO_TENANT_ID:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_demo_403_body(settings.DEMO_SIGNUP_URL),
            )
    except HTTPException:
        raise
    except Exception:
        pass


class DemoModeMiddleware(BaseHTTPMiddleware):
    """Middleware that blocks write operations on the demo tenant.

    Reads ``request.state.tenant_id`` set by TenantContextMiddleware.
    Only runs when DEMO_MODE=True and DEMO_TENANT_ID is configured.
    Admin seed/reset paths are exempted so the daily reset task can run.
    """

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        if (
            settings.DEMO_MODE
            and settings.DEMO_TENANT_ID
            and request.method in _WRITE_METHODS
            and request.url.path not in _DEMO_ADMIN_PATHS
        ):
            tenant_id = getattr(request.state, "tenant_id", None)
            if tenant_id and str(tenant_id) == settings.DEMO_TENANT_ID:
                logger.info(
                    "Demo write blocked: %s %s", request.method, request.url.path
                )
                body = _demo_403_body(settings.DEMO_SIGNUP_URL)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content=body,
                )

        return await call_next(request)
