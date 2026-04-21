"""
OWASP: CSRF protection for state-changing requests.

Uses double-submit cookie pattern:
- Server sets X-CSRF-Token cookie (SameSite=Strict) on first request
- Client sends X-CSRF-Token header on POST/PUT/DELETE/PATCH
- Server validates header matches cookie
"""

import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "heliox_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection for state-changing requests.
    Skips validation for API key auth (X-API-Key) and public endpoints.
    """

    SKIP_PATHS = {
        "/health",
        "/health/db",
        "/ready",
        "/readiness",
        "/liveness",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/public",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/google",
        "/api/v1/auth/set-session",
        "/api/v1/auth/logout",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        if not getattr(settings, "CSRF_PROTECTION_ENABLED", True):
            return await call_next(request)

        path = request.url.path
        method = request.method

        # Skip for safe methods
        if method in SAFE_METHODS:
            response = await call_next(request)
            return self._maybe_set_csrf_cookie(request, response)

        # Skip for API key auth (stateless)
        if request.headers.get("X-API-Key"):
            return await call_next(request)

        # Skip for excluded paths
        skip_csrf = any(
            path == skip or path.startswith(skip.rstrip("/") + "/") or path == skip.rstrip("/")
            for skip in self.SKIP_PATHS
        )
        if skip_csrf:
            response = await call_next(request)
            return self._maybe_set_csrf_cookie(request, response)

        # Validate CSRF for cookie-authenticated state-changing requests
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)
        session_cookie = request.cookies.get(settings.AUTH_COOKIE_NAME)

        # If no session cookie, no CSRF risk (no auth to protect)
        if not session_cookie:
            response = await call_next(request)
            return self._maybe_set_csrf_cookie(request, response)

        # Require CSRF token when session exists
        if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF validation failed"},
            )

        response = await call_next(request)
        return self._maybe_set_csrf_cookie(request, response)

    def _maybe_set_csrf_cookie(self, request: Request, response: Response) -> Response:
        """Set CSRF cookie if not present (for same-origin form submissions)."""
        if CSRF_COOKIE_NAME not in request.cookies and hasattr(response, "set_cookie"):
            token = secrets.token_urlsafe(32)
            secure = get_settings().ENV in ("production", "staging")
            response.set_cookie(
                CSRF_COOKIE_NAME,
                token,
                max_age=60 * 60 * 24 * 7,  # 7 days
                httponly=False,  # JS needs to read for header
                secure=secure,
                samesite="strict",
                path="/",
            )
        return response
