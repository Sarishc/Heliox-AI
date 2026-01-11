"""In-memory rate limiting middleware for MVP."""
import json
import time
from collections import defaultdict
from typing import Dict

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import get_request_id
from app.core.config import get_settings

settings = get_settings()

# In-memory storage for rate limiting (per-client)
# Format: {client_id: [(timestamp, path), ...]}
_rate_limit_store: Dict[str, list] = defaultdict(list)

# Rate limit configuration
RATE_LIMIT_WINDOW_SECONDS = 60  # 1 minute window
RATE_LIMIT_MAX_REQUESTS = 100  # Max requests per window per client


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


def is_rate_limited(client_id: str, path: str) -> bool:
    """
    Check if client has exceeded rate limit.
    
    Args:
        client_id: Client identifier
        path: Request path
        
    Returns:
        True if rate limited, False otherwise
    """
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW_SECONDS
    
    # Get request history for this client
    requests = _rate_limit_store.get(client_id, [])
    
    # Filter to requests within the current window
    recent_requests = [
        (ts, p) for ts, p in requests
        if ts >= window_start
    ]
    
    # Check if limit exceeded
    if len(recent_requests) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    
    # Add current request
    recent_requests.append((current_time, path))
    _rate_limit_store[client_id] = recent_requests
    
    # Cleanup old entries (keep only last window worth)
    _rate_limit_store[client_id] = [
        (ts, p) for ts, p in recent_requests
        if ts >= window_start
    ]
    
    return False


def get_retry_after(client_id: str) -> int:
    """
    Calculate retry-after seconds for rate-limited client.
    
    Args:
        client_id: Client identifier
        
    Returns:
        Seconds until next request is allowed
    """
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW_SECONDS
    
    requests = _rate_limit_store.get(client_id, [])
    if not requests:
        return RATE_LIMIT_WINDOW_SECONDS
    
    # Find oldest request in window
    oldest_time = min(ts for ts, _ in requests if ts >= window_start)
    if oldest_time:
        retry_after = int(window_start + RATE_LIMIT_WINDOW_SECONDS - current_time)
        return max(1, retry_after)
    
    return RATE_LIMIT_WINDOW_SECONDS


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using in-memory storage.
    
    Limits requests per client (API key or IP) to prevent abuse.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and public endpoints
        if request.url.path in ["/health", "/health/db", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        
        # Skip rate limiting for public endpoints
        if request.url.path.startswith("/api/v1/public"):
            return await call_next(request)
        
        client_id = get_client_id(request)
        path = request.url.path
        
        if is_rate_limited(client_id, path):
            request_id = get_request_id()
            retry_after = get_retry_after(client_id)
            
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
        
        # Add rate limit headers
        requests = _rate_limit_store.get(client_id, [])
        current_time = time.time()
        window_start = current_time - RATE_LIMIT_WINDOW_SECONDS
        remaining = RATE_LIMIT_MAX_REQUESTS - len([
            (ts, p) for ts, p in requests if ts >= window_start
        ])
        
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Window"] = str(RATE_LIMIT_WINDOW_SECONDS)
        
        return response
