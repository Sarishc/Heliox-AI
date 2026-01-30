"""Google OAuth authentication implementation."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.oauth_identity import OAuthIdentity, OAuthProvider
from app.models.user import User
from app.models.team import Team
from app.models.team_member import TeamMember

logger = logging.getLogger(__name__)
settings = get_settings()

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# OAuth state cache (in production, use Redis)
# Format: {state: {team_id, nonce, created_at, redirect_uri}}
_state_cache: Dict[str, dict] = {}


def generate_state_nonce() -> Tuple[str, str]:
    """
    Generate secure state and nonce for OAuth flow.
    
    Returns:
        Tuple of (state, nonce)
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    return state, nonce


def store_oauth_state(state: str, team_id: str, nonce: str, redirect_uri: str):
    """
    Store OAuth state for validation.
    
    Args:
        state: OAuth state token
        team_id: Team ID for this OAuth flow
        nonce: Nonce for validation
        redirect_uri: Redirect URI after OAuth
    """
    _state_cache[state] = {
        "team_id": team_id,
        "nonce": nonce,
        "redirect_uri": redirect_uri,
        "created_at": datetime.utcnow()
    }
    
    # Cleanup old states (older than 10 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    expired = [k for k, v in _state_cache.items() if v["created_at"] < cutoff]
    for k in expired:
        del _state_cache[k]


def validate_and_pop_state(state: str) -> Optional[dict]:
    """
    Validate OAuth state and remove from cache.
    
    Args:
        state: OAuth state token
        
    Returns:
        State data if valid, None otherwise
    """
    state_data = _state_cache.pop(state, None)
    
    if not state_data:
        logger.warning(f"Invalid or expired OAuth state: {state}")
        return None
    
    # Check if state is not too old (10 minutes)
    if datetime.utcnow() - state_data["created_at"] > timedelta(minutes=10):
        logger.warning(f"Expired OAuth state: {state}")
        return None
    
    return state_data


def build_google_auth_url(team_id: str, redirect_uri: str) -> Tuple[str, str]:
    """
    Build Google OAuth authorization URL.
    
    Args:
        team_id: Team ID for this OAuth flow
        redirect_uri: Redirect URI after OAuth
        
    Returns:
        Tuple of (auth_url, state)
    """
    # Generate state and nonce
    state, nonce = generate_state_nonce()
    
    # Store state for validation
    store_oauth_state(state, team_id, nonce, redirect_uri)
    
    # Build authorization URL
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "access_type": "offline",  # Get refresh token
        "prompt": "select_account",  # Force account selection
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    
    logger.info(f"Generated Google OAuth URL for team {team_id}")
    return auth_url, state


async def exchange_code_for_token(code: str, redirect_uri: str) -> Dict:
    """
    Exchange authorization code for access token.
    
    Args:
        code: Authorization code from Google
        redirect_uri: Redirect URI used in auth request
        
    Returns:
        Token response from Google
        
    Raises:
        Exception if token exchange fails
    """
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=data)
        
        if response.status_code != 200:
            error_detail = response.json() if response.text else "Unknown error"
            logger.error(f"Google token exchange failed: {error_detail}")
            raise Exception(f"Failed to exchange code for token: {error_detail}")
        
        return response.json()


async def get_google_userinfo(access_token: str) -> Dict:
    """
    Get user info from Google.
    
    Args:
        access_token: Google access token
        
    Returns:
        User info from Google
        
    Raises:
        Exception if userinfo request fails
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
        
        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"Google userinfo request failed: {error_detail}")
            raise Exception(f"Failed to get user info: {error_detail}")
        
        return response.json()


def check_domain_allowed(email: str, team: Team) -> bool:
    """
    Check if email domain is allowed for team SSO.
    
    Args:
        email: User email address
        team: Team object
        
    Returns:
        True if domain is allowed, False otherwise
    """
    if not team.sso_enforce_domain:
        # Domain enforcement disabled
        return True
    
    if not team.allowed_email_domains:
        # No domains configured, allow all
        return True
    
    email_domain = email.split("@")[-1].lower()
    
    # Check if domain is in allowed list
    allowed = any(
        email_domain == domain.lower()
        for domain in team.allowed_email_domains
    )
    
    if not allowed:
        logger.warning(
            f"Email {email} domain not allowed for team {team.id}. "
            f"Allowed domains: {team.allowed_email_domains}"
        )
    
    return allowed


def upsert_oauth_identity(
    db: Session,
    team_id: str,
    user: User,
    provider_user_id: str,
    email: str,
    email_verified: bool,
    name: Optional[str],
    picture: Optional[str],
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None
) -> OAuthIdentity:
    """
    Create or update OAuth identity.
    
    Args:
        db: Database session
        team_id: Team ID
        user: User object
        provider_user_id: Provider's user ID
        email: User email
        email_verified: Whether email is verified
        name: User's full name
        picture: Profile picture URL
        access_token: OAuth access token (optional)
        refresh_token: OAuth refresh token (optional)
        expires_in: Token expiration in seconds (optional)
        
    Returns:
        OAuthIdentity object
    """
    # Check if identity already exists
    identity = db.query(OAuthIdentity).filter(
        OAuthIdentity.provider == OAuthProvider.GOOGLE,
        OAuthIdentity.provider_user_id == provider_user_id
    ).first()
    
    if identity:
        # Update existing identity
        identity.user_id = user.id
        identity.team_id = team_id
        identity.email = email
        identity.email_verified = email_verified
        identity.name = name
        identity.picture = picture
        identity.last_login_at = datetime.utcnow()
        
        # Update tokens if provided (encrypt in production)
        if access_token:
            identity.access_token_encrypted = access_token  # TODO: Encrypt
        if refresh_token:
            identity.refresh_token_encrypted = refresh_token  # TODO: Encrypt
        if expires_in:
            identity.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        logger.info(f"Updated OAuth identity for user {user.id}")
    else:
        # Create new identity
        identity = OAuthIdentity(
            team_id=team_id,
            user_id=user.id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=email_verified,
            name=name,
            picture=picture,
            access_token_encrypted=access_token,  # TODO: Encrypt
            refresh_token_encrypted=refresh_token,  # TODO: Encrypt
            token_expires_at=datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None,
            last_login_at=datetime.utcnow()
        )
        db.add(identity)
        logger.info(f"Created OAuth identity for user {user.id}")
    
    db.commit()
    db.refresh(identity)
    
    return identity


def get_or_create_user_from_oauth(
    db: Session,
    team_id: str,
    email: str,
    name: Optional[str],
    email_verified: bool
) -> User:
    """
    Get existing user or create new user from OAuth data.
    
    Args:
        db: Database session
        team_id: Team ID
        email: User email
        name: User's full name
        email_verified: Whether email is verified
        
    Returns:
        User object
    """
    # Check if user already exists
    user = db.query(User).filter(User.email == email).first()
    
    if user:
        logger.info(f"Found existing user for email {email}")
        
        # Check if user is member of this team
        membership = db.query(TeamMember).filter(
            TeamMember.user_id == user.id,
            TeamMember.team_id == team_id
        ).first()
        
        if not membership:
            # Add user to team
            membership = TeamMember(
                user_id=user.id,
                team_id=team_id,
                role="member"
            )
            db.add(membership)
            db.commit()
            logger.info(f"Added user {user.id} to team {team_id}")
        
        return user
    
    # Create new user (password not needed for SSO users)
    user = User(
        email=email,
        full_name=name,
        hashed_password=secrets.token_urlsafe(32),  # Random password (not used)
        is_active=True
    )
    db.add(user)
    db.flush()
    
    # Add user to team
    membership = TeamMember(
        user_id=user.id,
        team_id=team_id,
        role="member"
    )
    db.add(membership)
    db.commit()
    db.refresh(user)
    
    logger.info(f"Created new user {user.id} for email {email}")
    
    return user
