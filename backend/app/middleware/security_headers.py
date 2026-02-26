"""
OWASP: Security headers and HTTPS enforcement.

- HTTPS redirect (production/staging)
- HSTS
- CSP, X-Frame-Options, X-Content-Type-Options
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Default CSP - restrict to same-origin for API
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        # HTTPS redirect (production/staging only)
        if settings.ENV in ("production", "staging"):
            scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
            if scheme == "http" and request.url.path not in ["/health", "/health/db", "/ready", "/readiness", "/liveness", "/metrics"]:
                url = request.url.replace(scheme="https")
                return RedirectResponse(url=url, status_code=301)

        response = await call_next(request)

        # HSTS (production/staging)
        if settings.ENV in ("production", "staging"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy, CSP is preferred)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content-Security-Policy (for API, minimal)
        response.headers["Content-Security-Policy"] = DEFAULT_CSP

        # Permissions-Policy (disable unnecessary features)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        return response
