"""Middleware for enforcing subscription plan entitlements."""
import logging
from typing import Callable, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.billing import TeamEntitlement
from app.billing.plans import check_limit, check_feature

logger = logging.getLogger(__name__)


class EntitlementCheckMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce plan entitlements.
    
    Checks plan limits before allowing API requests:
    - API call limits (daily)
    - Feature access (integrations, forecasting, etc.)
    
    Returns 402 Payment Required if limit exceeded.
    """
    
    # Paths that require specific features
    FEATURE_REQUIRED_PATHS = {
        "/api/v1/integrations": "integrations_enabled",
        "/api/v1/forecast": "forecasting_enabled",
        "/api/v1/reports": "custom_reports"
    }
    
    # Paths to skip entitlement check
    EXCLUDED_PATHS = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/billing",  # Allow billing endpoints
        "/api/v1/auth"      # Allow auth endpoints
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Check entitlements before processing request.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response or error if entitlement violated
        """
        # Skip check for excluded paths
        if self._should_skip_check(request):
            return await call_next(request)
        
        # Get team_id from request state (set by auth middleware)
        team_id = getattr(request.state, "team_id", None)
        
        if not team_id:
            # No team_id means not authenticated, let auth handle it
            return await call_next(request)
        
        # Get entitlements
        db = next(get_db())
        try:
            entitlement = db.query(TeamEntitlement).filter(
                TeamEntitlement.team_id == team_id
            ).first()
            
            if not entitlement:
                # No entitlement record, allow (will be created on subscription endpoint)
                return await call_next(request)
            
            # Check feature access
            feature_check = self._check_feature_access(request, entitlement)
            if feature_check:
                return feature_check
            
            # Process request
            response = await call_next(request)
            return response
        
        finally:
            db.close()
    
    def _should_skip_check(self, request: Request) -> bool:
        """
        Determine if entitlement check should be skipped.
        
        Args:
            request: Incoming request
            
        Returns:
            True if check should be skipped
        """
        path = request.url.path
        
        # Skip specific paths
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return True
        
        return False
    
    def _check_feature_access(self, request: Request, entitlement: TeamEntitlement) -> Optional[JSONResponse]:
        """
        Check if team has access to requested feature.
        
        Args:
            request: Incoming request
            entitlement: Team entitlement
            
        Returns:
            Error response if access denied, None if allowed
        """
        path = request.url.path
        
        # Check if path requires a specific feature
        for path_prefix, feature_key in self.FEATURE_REQUIRED_PATHS.items():
            if path.startswith(path_prefix):
                if not check_feature({"features": entitlement.features}, feature_key):
                    logger.warning(
                        f"Team {entitlement.team_id} attempted to access {path} "
                        f"but feature {feature_key} not enabled"
                    )
                    return JSONResponse(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        content={
                            "error": "Feature not available",
                            "message": f"Your plan does not include access to this feature. "
                                      f"Please upgrade your subscription to unlock {feature_key.replace('_', ' ')}.",
                            "feature": feature_key,
                            "plan": entitlement.plan.value,
                            "upgrade_url": "/billing"
                        }
                    )
        
        return None
