"""SAML 2.0 authentication for Okta and other IdPs."""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

_SAML_AVAILABLE: Optional[bool] = None
_SAML_IMPORT_ERROR: Optional[str] = None


def _ensure_saml_imported() -> None:
    global _SAML_AVAILABLE, _SAML_IMPORT_ERROR
    if _SAML_AVAILABLE is not None:
        return
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth  # noqa: F401
        from onelogin.saml2.metadata import OneLogin_Saml2_Metadata  # noqa: F401
        from onelogin.saml2.settings import OneLogin_Saml2_Settings  # noqa: F401
        _SAML_AVAILABLE = True
        _SAML_IMPORT_ERROR = None
    except Exception as e:
        _SAML_AVAILABLE = False
        _SAML_IMPORT_ERROR = str(e)

from app.core.config import get_settings
from app.core.security import create_access_token
from app.auth.security import ACCESS_TOKEN_EXPIRE_MINUTES
from app.models.team import Team
from app.models.team_saml_config import TeamSamlConfig
from app.models.user import User
from app.models.team_member import TeamMember, TeamRole
from app.models.oauth_identity import OAuthIdentity, OAuthProvider

logger = logging.getLogger(__name__)
settings = get_settings()

# State cache for SAML flow (team_id, relay_state) - use Redis in production
_saml_state_cache: Dict[str, dict] = {}


def _get_saml_classes():
    _ensure_saml_imported()
    if not _SAML_AVAILABLE:
        raise ValueError("SAML not available")
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.metadata import OneLogin_Saml2_Metadata
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    return OneLogin_Saml2_Auth, OneLogin_Saml2_Metadata, OneLogin_Saml2_Settings


def _build_saml_settings(
    team_id: str,
    saml_config: TeamSamlConfig,
    acs_url: str,
    slo_url: Optional[str] = None,
):
    """Build python3-saml settings dict for a team."""
    base_url = settings.FRONTEND_URL or "http://localhost:3000"
    api_base = settings.API_BASE_URL or "http://localhost:8000"
    sp_entity_id = f"{api_base}/api/v1/auth/saml/metadata"
    sp_acs = acs_url or f"{api_base}/api/v1/auth/saml/acs"

    sp_config = {
        "entityId": sp_entity_id,
        "assertionConsumerService": {
            "url": sp_acs,
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        },
        "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        "x509cert": "",
        "privateKey": "",
    }
    if slo_url:
        sp_config["singleLogoutService"] = {
            "url": slo_url,
            "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        }

    _, _, OneLogin_Saml2_Settings = _get_saml_classes()
    config = {
        "strict": True,
        "debug": settings.ENV == "dev",
        "sp": sp_config,
        "idp": {
            "entityId": saml_config.idp_entity_id,
            "singleSignOnService": {
                "url": saml_config.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": saml_config.idp_x509_cert,
        },
    }
    return OneLogin_Saml2_Settings(config)


def store_saml_state(team_id: str, relay_state: Optional[str] = None) -> str:
    """Store state for SAML flow validation. Returns state token."""
    state = secrets.token_urlsafe(32)
    _saml_state_cache[state] = {
        "team_id": team_id,
        "relay_state": relay_state,
        "created_at": datetime.utcnow(),
    }
    # Cleanup old (10 min)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    for k in list(_saml_state_cache.keys()):
        if _saml_state_cache[k]["created_at"] < cutoff:
            del _saml_state_cache[k]
    return state


def validate_and_pop_saml_state(state: str) -> Optional[dict]:
    """Validate and consume SAML state."""
    data = _saml_state_cache.pop(state, None)
    if not data:
        return None
    if datetime.utcnow() - data["created_at"] > timedelta(minutes=10):
        return None
    return data


def init_saml_login(
    db: Session,
    team_id: str,
    relay_state: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Initiate SAML login. Returns (redirect_url, state).
    Raises ValueError if team has no valid SAML config.
    """
    _check_saml_available()
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise ValueError("Team not found")

    saml_config = (
        db.query(TeamSamlConfig)
        .filter(
            TeamSamlConfig.team_id == team_id,
            TeamSamlConfig.enabled == True,
        )
        .first()
    )
    if not saml_config:
        raise ValueError("SAML is not configured for this team")

    api_base = settings.API_BASE_URL or "http://localhost:8000"
    acs_url = f"{api_base}/api/v1/auth/saml/acs"
    saml_settings = _build_saml_settings(str(team_id), saml_config, acs_url)

    OneLogin_Saml2_Auth, _, _ = _get_saml_classes()
    state = store_saml_state(str(team_id), relay_state)
    auth = OneLogin_Saml2_Auth(
        _prepare_request_for_toolkit(relay_state=state),
        saml_settings.get_settings_data(),
    )
    redirect_url = auth.login(return_to=state)
    return redirect_url, state


def _prepare_request_for_toolkit(
    request_method: str = "GET",
    get_data: Optional[Dict] = None,
    post_data: Optional[Dict] = None,
    relay_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Build request dict for OneLogin_Saml2_Auth."""
    return {
        "https": "on" if getattr(settings, "ENV", "dev") in ("production", "staging") else "off",
        "http_host": "localhost",
        "server_port": 8000,
        "script_name": "",
        "get_data": get_data or {},
        "post_data": post_data or {},
        "request_uri": "/api/v1/auth/saml/acs",
        "query_string": "",
        "request_method": request_method,
    }


def process_saml_response(
    db: Session,
    saml_response: str,
    relay_state: str,
) -> Tuple[User, UUID, str]:
    """
    Process SAML response. Returns (user, team_id, session_token).
    Raises ValueError on validation failure.
    """
    _check_saml_available()
    state_data = validate_and_pop_saml_state(relay_state)
    if not state_data:
        raise ValueError("Invalid or expired SAML state")

    team_id = state_data["team_id"]
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise ValueError("Team not found")

    saml_config = (
        db.query(TeamSamlConfig)
        .filter(
            TeamSamlConfig.team_id == team_id,
            TeamSamlConfig.enabled == True,
        )
        .first()
    )
    if not saml_config:
        raise ValueError("SAML is not configured for this team")

    api_base = settings.API_BASE_URL or "http://localhost:8000"
    acs_url = f"{api_base}/api/v1/auth/saml/acs"
    saml_settings = _build_saml_settings(team_id, saml_config, acs_url)

    OneLogin_Saml2_Auth, _, _ = _get_saml_classes()
    auth = OneLogin_Saml2_Auth(
        _prepare_request_for_toolkit(
            request_method="POST",
            post_data={"SAMLResponse": saml_response, "RelayState": relay_state},
        ),
        saml_settings.get_settings_data(),
    )
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        logger.warning(f"SAML validation errors: {errors}")
        raise ValueError(f"SAML validation failed: {errors[0] if errors else 'Unknown'}")

    attrs = auth.get_attributes()
    name_id = auth.get_nameid()
    email = (
        attrs.get("email")[0]
        if attrs.get("email")
        else attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress", [None])[0]
        or name_id
    )
    name = (
        attrs.get("name")[0]
        if attrs.get("name")
        else attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name", [None])[0]
    )
    if not email:
        raise ValueError("SAML assertion missing email")

    # Domain check if team enforces
    if team.sso_enforce_domain and team.allowed_email_domains:
        domain = email.split("@")[-1].lower()
        if domain not in [d.lower() for d in team.allowed_email_domains]:
            raise ValueError("Email domain not allowed for this team")

    # JIT provision or match existing user
    user = _get_or_create_user_saml(
        db=db,
        team_id=UUID(team_id),
        email=email,
        name=name,
        provider_user_id=name_id or email,
        saml_config=saml_config,
    )

    # Upsert OAuthIdentity for SAML (provider=OKTA)
    _upsert_saml_identity(db, user.id, UUID(team_id), provider_user_id=name_id or email, email=email, name=name)

    session_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return user, UUID(team_id), session_token


def _get_or_create_user_saml(
    db: Session,
    team_id: UUID,
    email: str,
    name: Optional[str],
    provider_user_id: str,
    saml_config: TeamSamlConfig,
) -> User:
    """Get existing user or JIT provision. Assign default role from config."""
    user = db.query(User).filter(User.email == email).first()
    default_role = TeamRole.VIEWER
    try:
        default_role = TeamRole(saml_config.default_role)
    except ValueError:
        pass

    if user:
        membership = (
            db.query(TeamMember)
            .filter(TeamMember.user_id == user.id, TeamMember.team_id == team_id)
            .first()
        )
        if not membership:
            db.add(
                TeamMember(user_id=user.id, team_id=team_id, role=default_role)
            )
            db.commit()
        return user

    user = User(
        email=email,
        full_name=name,
        hashed_password=secrets.token_urlsafe(32),
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(TeamMember(user_id=user.id, team_id=team_id, role=default_role))
    db.commit()
    db.refresh(user)
    logger.info(f"JIT provisioned user {user.id} for SAML login")
    return user


def _upsert_saml_identity(
    db: Session,
    user_id: UUID,
    team_id: UUID,
    provider_user_id: str,
    email: str,
    name: Optional[str],
) -> OAuthIdentity:
    """Create or update OAuthIdentity for SAML (Okta)."""
    identity = (
        db.query(OAuthIdentity)
        .filter(
            OAuthIdentity.provider == OAuthProvider.OKTA,
            OAuthIdentity.provider_user_id == provider_user_id,
        )
        .first()
    )
    if identity:
        identity.user_id = user_id
        identity.team_id = team_id
        identity.email = email
        identity.name = name
        identity.last_login_at = datetime.utcnow()
    else:
        identity = OAuthIdentity(
            team_id=team_id,
            user_id=user_id,
            provider=OAuthProvider.OKTA,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=True,
            name=name,
            last_login_at=datetime.utcnow(),
        )
        db.add(identity)
    db.commit()
    db.refresh(identity)
    return identity


def get_sp_metadata(team_id: str, saml_config: TeamSamlConfig) -> str:
    """Generate SP metadata XML for IdP configuration."""
    _check_saml_available()
    api_base = settings.API_BASE_URL or "http://localhost:8000"
    acs_url = f"{api_base}/api/v1/auth/saml/acs"
    saml_settings = _build_saml_settings(team_id, saml_config, acs_url)
    _, OneLogin_Saml2_Metadata, _ = _get_saml_classes()
    metadata_gen = OneLogin_Saml2_Metadata(
        saml_settings.get_settings_data(),
        False,
        None,
        None,
    )
    return metadata_gen.get_metadata()
