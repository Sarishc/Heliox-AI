"""Redis-backed rate limiting middleware."""
import json
import time
import logging
from typing import Optional

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import get_request_id
from app.core.config import get_settings
from app.core.cache import get_redis

settings = get_settings()
logger = logging.getLogger(__name__)

# Rate limit configuration (OWASP: 100/min per user, 5/min for login)
RATE_LIMIT_WINDOW_SECONDS = int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60))
RATE_LIMIT_MAX_REQUESTS = int(getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 100))
LOGIN_PATH = "/api/v1/auth/login"
_LOCAL_LIMITS: dict[str, tuple[int, int]] = {}


def _local_is_rate_limited(client_id: str) -> tuple[bool, int]:
    current_time = int(time.time())
    window_start = current_time - (current_time % RATE_LIMIT_WINDOW_SECONDS)
    count, stored_window = _LOCAL_LIMITS.get(client_id, (0, window_start))
    if stored_window != window_start:
        count = 0
        stored_window = window_start
    count += 1
    _LOCAL_LIMITS[client_id] = (count, stored_window)
    if count > RATE_LIMIT_MAX_REQUESTS:
        retry_after = window_start + RATE_LIMIT_WINDOW_SECONDS - current_time
        return True, max(1, retry_after)
    return False, RATE_LIMIT_WINDOW_SECONDS


def get_client_id(request: Request) -> str:
    """
    Get client identifier for rate limiting.
    
    Uses X-API-Key header if present (team API key), otherwise falls back to IP.
    """
    # Try API key first (more granular)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Use hash of API key (don't store raw key)
        import hashlib
        return f"api_key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
    
    # Fall back to IP address
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def is_rate_limited(client_id: str, path: str) -> tuple[bool, int]:
    """
    Check if client has exceeded rate limit.
    
    Args:
        client_id: Client identifier
        path: Request path
        
    Returns:
        True if rate limited, False otherwise
    """
    current_time = int(time.time())
    window_start = current_time - (current_time % RATE_LIMIT_WINDOW_SECONDS)
    key = f"rl:{client_id}:{window_start}"
    redis_client = get_redis()
    if not redis_client:
        logger.warning("Redis unavailable for rate limiting; falling back to local limiter")
        return _local_is_rate_limited(client_id)
    
    try:
        count = redis_client.incr(key)
        if count == 1:
            redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS * 2)
        
        if count > RATE_LIMIT_MAX_REQUESTS:
            retry_after = window_start + RATE_LIMIT_WINDOW_SECONDS - current_time
            return True, max(1, retry_after)
        
        return False, RATE_LIMIT_WINDOW_SECONDS
    except Exception:
        logger.warning("Redis error for rate limiting; falling back to local limiter", exc_info=True)
        return _local_is_rate_limited(client_id)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using in-memory storage.
    
    Limits requests per client (API key or IP) to prevent abuse.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and public endpoints
        if request.url.path in ["/health", "/health/db", "/ready", "/readiness", "/liveness", "/metrics", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        if request.url.path.startswith("/api/v1/public"):
            return await call_next(request)

        # Login has its own stricter limit (5/min) in auth.brute_force
        if request.url.path == LOGIN_PATH:
            return await call_next(request)

        client_id = get_client_id(request)
        path = request.url.path
        
        limited, retry_after = is_rate_limited(client_id, path)
        if limited:
            request_id = get_request_id()
            
            return Response(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=json.dumps({
                    "error": "rate_limit_exceeded",
                    "message": "Rate limit exceeded. Please try again later.",
                    "request_id": request_id,
                    "retry_after": retry_after
                }),
                media_type="application/json",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(RATE_LIMIT_MAX_REQUESTS),
                    "X-RateLimit-Window": str(RATE_LIMIT_WINDOW_SECONDS),
                    "X-Request-ID": request_id,
                }
            )
        
        response = await call_next(request)
        
        # Add rate limit headers (best-effort)
        remaining = max(0, RATE_LIMIT_MAX_REQUESTS - 1)
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Window"] = str(RATE_LIMIT_WINDOW_SECONDS)
        
        return response
