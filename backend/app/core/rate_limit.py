"""Redis-backed rate limiting middleware.

Buckets are keyed by identities a client can't mint by editing headers:

- a valid session (JWT signature, expiry and logout are checked) -> ``user:<hash>``
- an X-API-Key -> ``api_key:<hash>``, plus a per-client ceiling on all API-key
  traffic so rotating made-up keys can't create unlimited fresh buckets
- otherwise the client address from app.core.client_ip -> ``ip:<address>``

Keys are ``rl:<bucket>:<window>`` with a 2-window TTL, so buckets from the
previous scheme (``rl:ip:<peer>``) simply age out.
"""

import hashlib
import json
import logging
from typing import Optional

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.client_ip import get_client_address
from app.core.logging import get_request_id
from app.core.config import get_settings
from app.core.cache import require_redis

# Failing open on rate limiting is a security risk — a Redis outage must not
# silently disable rate limiting. require_redis() raises HTTP 503 on failure.

settings = get_settings()
logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW_SECONDS = int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60))
RATE_LIMIT_MAX_REQUESTS = int(getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 100))
# One client address may run several API keys at full rate, but no more than this many
API_KEY_CLIENT_MULTIPLIER = 5
LOGIN_PATH = "/api/v1/auth/login"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _session_subject(request: Request) -> Optional[str]:
    """Subject of a valid, non-revoked session token, or None. Raises 503 if Redis is down."""
    import jwt

    from app.auth.cookie_auth import get_token_from_cookie_or_header, is_token_blacklisted
    from app.auth.security import SECRET_KEY

    token = get_token_from_cookie_or_header(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
    try:
        if is_token_blacklisted(token):
            return None
    except HTTPException:
        raise
    except Exception:
        return None
    subject = payload.get("sub")
    return str(subject).lower() if subject else None


def get_rate_limit_buckets(request: Request) -> list[tuple[str, int]]:
    """(bucket, limit) pairs this request counts against."""
    subject = _session_subject(request)
    if subject:
        return [(f"user:{_digest(subject)}", RATE_LIMIT_MAX_REQUESTS)]

    client = get_client_address(request)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return [
            (f"api_key:{_digest(api_key)}", RATE_LIMIT_MAX_REQUESTS),
            (f"api_key_client:{client.bucket}", RATE_LIMIT_MAX_REQUESTS * API_KEY_CLIENT_MULTIPLIER),
        ]
    return [(f"ip:{client.bucket}", RATE_LIMIT_MAX_REQUESTS)]


def get_client_id(request: Request) -> str:
    """Primary rate-limit identity for this request (see get_rate_limit_buckets)."""
    return get_rate_limit_buckets(request)[0][0]


def is_rate_limited(client_id: str, path: str, limit: Optional[int] = None) -> tuple[bool, int]:
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

    if count > (limit if limit is not None else RATE_LIMIT_MAX_REQUESTS):
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

        path = request.url.path

        try:
            limited, retry_after = False, RATE_LIMIT_WINDOW_SECONDS
            # Every bucket is counted, so rotating identities can't skip the ceiling
            for client_id, limit in get_rate_limit_buckets(request):
                bucket_limited, bucket_retry = is_rate_limited(client_id, path, limit)
                if bucket_limited and (not limited or bucket_retry > retry_after):
                    limited, retry_after = True, bucket_retry
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
