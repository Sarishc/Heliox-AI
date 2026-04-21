"""Redis-backed rate limiting middleware."""

import json
import logging

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import get_request_id
from app.core.config import get_settings
from app.core.cache import require_redis

# Failing open on rate limiting is a security risk — a Redis outage must not
# silently disable rate limiting. require_redis() raises HTTP 503 on failure.

settings = get_settings()
logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SECONDS = int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60))
RATE_LIMIT_MAX_REQUESTS = int(getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 100))
LOGIN_PATH = "/api/v1/auth/login"


def get_client_id(request: Request) -> str:
    """
    Get client identifier for rate limiting.

    Uses X-API-Key header if present (team API key), otherwise falls back to IP.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        import hashlib

        return f"api_key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def is_rate_limited(client_id: str, path: str) -> tuple[bool, int]:
    """
    Check if client has exceeded rate limit.

    Raises HTTP 503 if Redis is unavailable — failing open is not acceptable.
    """
    import time

    current_time = int(time.time())
    window_start = current_time - (current_time % RATE_LIMIT_WINDOW_SECONDS)
    key = f"rl:{client_id}:{window_start}"

    redis_client = require_redis()

    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS * 2)

    if count > RATE_LIMIT_MAX_REQUESTS:
        retry_after = window_start + RATE_LIMIT_WINDOW_SECONDS - current_time
        return True, max(1, retry_after)

    return False, RATE_LIMIT_WINDOW_SECONDS


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and public endpoints
        if request.url.path in [
            "/health",
            "/health/db",
            "/ready",
            "/readiness",
            "/liveness",
            "/metrics",
            "/",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/v1/health",
        ]:
            return await call_next(request)
        if request.url.path.startswith("/api/v1/public"):
            return await call_next(request)

        # Login has its own stricter limit in auth.brute_force
        if request.url.path == LOGIN_PATH:
            return await call_next(request)

        client_id = get_client_id(request)
        path = request.url.path

        try:
            limited, retry_after = is_rate_limited(client_id, path)
        except Exception:
            # Redis error already logged by require_redis(); propagate as 503
            return Response(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=json.dumps(
                    {
                        "error": "service_unavailable",
                        "message": "Rate limiting service temporarily unavailable.",
                    }
                ),
                media_type="application/json",
            )

        if limited:
            request_id = get_request_id()
            return Response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=json.dumps(
                    {
                        "error": "rate_limit_exceeded",
                        "message": "Rate limit exceeded. Please try again later.",
                        "request_id": request_id,
                        "retry_after": retry_after,
                    }
                ),
                media_type="application/json",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(RATE_LIMIT_MAX_REQUESTS),
                    "X-RateLimit-Window": str(RATE_LIMIT_WINDOW_SECONDS),
                    "X-Request-ID": request_id,
                },
            )

        response = await call_next(request)

        remaining = max(0, RATE_LIMIT_MAX_REQUESTS - 1)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(RATE_LIMIT_WINDOW_SECONDS)

        return response
