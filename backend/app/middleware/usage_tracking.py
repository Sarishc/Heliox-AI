"""Middleware for tracking API usage."""
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.utils.usage_metering import record_api_request

logger = logging.getLogger(__name__)
settings = get_settings()


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track API usage for billing purposes.
    
    Records API requests per team for metering.
    Excludes health checks, docs, and static files.
    Supports configurable sampling rate.
    """
    
    # Paths to exclude from metering
    EXCLUDED_PATHS = {
        "/health",
        "/health/db",
        "/ready",
        "/readiness",
        "/liveness",
        "/metrics",
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico"
    }
    
    # Path prefixes to exclude
    EXCLUDED_PREFIXES = [
        "/static/",
        "/assets/"
    ]
    
    def __init__(self, app, sample_rate: float = 1.0):
        """
        Initialize middleware.
        
        Args:
            app: FastAPI app
            sample_rate: Sampling rate for API requests (0.0 to 1.0)
                        1.0 = track all requests (default)
                        0.1 = track 10% of requests (each counts as 10)
        """
        super().__init__(app)
        self.sample_rate = sample_rate
        logger.info(f"UsageTrackingMiddleware initialized with sample_rate={sample_rate}")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and record usage.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Process request
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Check if request should be metered
        if not self._should_meter_request(request):
            return response
        
        # Extract team_id from request state (set by auth middleware)
        team_id = getattr(request.state, "team_id", None)
        
        if team_id:
            try:
                # Record usage asynchronously (don't block response)
                record_api_request(
                    team_id=team_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    sample_rate=self.sample_rate
                )
            except Exception as e:
                # Log error but don't fail request
                logger.error(f"Failed to record API usage: {e}")
        
        # Add response time header for monitoring
        response.headers["X-Process-Time"] = f"{duration:.3f}"
        
        return response
    
    def _should_meter_request(self, request: Request) -> bool:
        """
        Determine if request should be metered.
        
        Args:
            request: Incoming request
            
        Returns:
            True if request should be metered
        """
        path = request.url.path
        
        # Exclude specific paths
        if path in self.EXCLUDED_PATHS:
            return False
        
        # Exclude path prefixes
        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return False
        
        # Meter all other requests
        return True
