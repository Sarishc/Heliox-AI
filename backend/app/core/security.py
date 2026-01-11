"""Security utilities for API authentication and authorization."""
import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging import get_request_id
from app.models.team import Team
from app.models.team_api_key import TeamAPIKey

settings = get_settings()
logger = logging.getLogger(__name__)


def verify_admin_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Verify admin API key from request headers.
    
    Checks the X-API-Key header against the configured ADMIN_API_KEY
    environment variable. Used to protect admin endpoints.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Returns:
        The verified API key
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
        
    Example:
        ```python
        @router.post("/admin/endpoint")
        def admin_endpoint(api_key: str = Depends(verify_admin_api_key)):
            # Protected admin logic here
            pass
        ```
    """
    request_id = get_request_id()
    
    # Check if admin API key is configured
    admin_api_key = getattr(settings, "ADMIN_API_KEY", None)
    
    if not admin_api_key:
        logger.error(
            "Admin API key not configured on server",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API key not configured on server"
        )
    
    # Check if API key was provided
    if not x_api_key:
        logger.warning(
            "Admin API key authentication failed: missing X-API-Key header",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Verify API key matches using constant-time comparison
    if not secrets.compare_digest(x_api_key, admin_api_key):
        logger.warning(
            "Admin API key authentication failed: invalid key",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    logger.debug(
        "Admin API key authentication successful",
        extra={"request_id": request_id}
    )
    
    return x_api_key


# Alias for backwards compatibility
get_api_key = verify_admin_api_key


def verify_team_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
) -> TeamAPIKey:
    """
    Verify team API key from request headers.
    
    Checks the X-API-Key header against team API keys in the database.
    Uses constant-time comparison to prevent timing attacks.
    
    Args:
        x_api_key: API key from X-API-Key header
        db: Database session
        
    Returns:
        TeamAPIKey instance
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
        
    Example:
        ```python
        @router.get("/teams/{team_id}/costs")
        def get_costs(api_key: TeamAPIKey = Depends(verify_team_api_key)):
            # API key is valid, use api_key.team_id for authorization
            pass
        ```
    """
    request_id = get_request_id()
    
    if not x_api_key:
        logger.warning(
            "Team API key authentication failed: missing X-API-Key header",
            extra={"request_id": request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Hash the provided key
    key_hash = TeamAPIKey.hash_key(x_api_key)
    
    # Look up API key by hash
    api_key = db.query(TeamAPIKey).filter(
        TeamAPIKey.key_hash == key_hash,
        TeamAPIKey.is_active == True
    ).first()
    
    if not api_key:
        # Log failed authentication attempt (without the key)
        logger.warning(
            "Team API key authentication failed: invalid key",
            extra={
                "request_id": request_id,
                "key_hash_prefix": key_hash[:8]  # Only log prefix for security
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Verify key using constant-time comparison
    if not api_key.verify_key(x_api_key):
        logger.warning(
            "Team API key authentication failed: key verification failed",
            extra={
                "request_id": request_id,
                "team_id": str(api_key.team_id),
                "key_name": api_key.key_name
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Update last_used_at
    api_key.last_used_at = datetime.utcnow()
    db.commit()
    
    # Log successful authentication (without sensitive data)
    logger.debug(
        "Team API key authentication successful",
        extra={
            "request_id": request_id,
            "team_id": str(api_key.team_id),
            "key_name": api_key.key_name
        }
    )
    
    return api_key


def get_team_from_api_key(
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    db: Session = Depends(get_db)
) -> Team:
    """
    Get team from verified API key.
    
    Convenience dependency that returns the Team associated with the API key.
    
    Args:
        api_key: Verified TeamAPIKey instance
        db: Database session
        
    Returns:
        Team instance
        
    Raises:
        HTTPException: 404 if team not found
    """
    team = db.query(Team).filter(Team.id == api_key.team_id).first()
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    return team

