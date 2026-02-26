"""Application configuration management using Pydantic Settings."""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application
    APP_NAME: str = "Heliox-AI"
    ENV: str = Field(default="dev", description="Environment: dev, staging, production")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    PORT: int = Field(default=8000, description="Server port (default: 8000, Railway uses PORT env var)")
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:postgres@postgres:5432/heliox",
        description="PostgreSQL connection string"
    )
    
    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string"
    )
    
    # CORS
    CORS_ENABLED: bool = Field(default=True, description="Enable CORS")
    CORS_ORIGINS: List[str] = Field(
        default=[],
        description="Allowed CORS origins (comma-separated list or JSON array). Required in production."
    )
    
    # API
    API_V1_PREFIX: str = "/api/v1"

    # Reports
    REPORT_STORAGE_PATH: str = Field(
        default="app/data/reports",
        description="Local filesystem path to store generated reports"
    )
    REPORT_SHARE_DEFAULT_TTL_DAYS: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Default share link expiration in days"
    )
    REPORT_SHARE_MAX_TTL_DAYS: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Maximum share link expiration in days"
    )
    REPORT_SHARE_BASE_URL: str = Field(
        default="",
        description="Base URL for share links (e.g., https://app.example.com)"
    )

    # Multi-tenant mode
    MULTI_TENANT: bool = Field(
        default=True,
        description="Enable multi-tenant isolation (requires team-scoped API keys)"
    )
    SINGLE_TENANT_TEAM_ID: str = Field(
        default="",
        description="Team ID to lock all queries to when MULTI_TENANT is false"
    )
    
    # Security - REQUIRED: No defaults for production safety
    SECRET_KEY: str = Field(
        description="Secret key for JWT token encoding (REQUIRED - set via environment variable)"
    )
    
    ADMIN_API_KEY: str = Field(
        default="",
        description="Deprecated: API key for admin endpoints. Prefer RBAC (is_platform_admin). Empty = use platform admin only."
    )
    
    # Integrations
    INTEGRATIONS_ENCRYPTION_KEY: str = Field(
        default="",
        description="Encryption key for integration configs (generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    )
    
    # Usage Metering
    USAGE_METERING_SAMPLE_RATE: float = Field(
        default=1.0,
        description="Sampling rate for API usage metering (1.0 = 100%, 0.1 = 10%)"
    )
    
    # Rate Limiting (OWASP)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        description="Time window for rate limiting (seconds)"
    )
    RATE_LIMIT_MAX_REQUESTS: int = Field(
        default=600,
        description="Max requests per window per user/IP (500 req/min target for 100 users)"
    )
    RATE_LIMIT_LOGIN_ATTEMPTS: int = Field(
        default=5,
        description="Max login attempts per minute per IP (OWASP: 5/min)"
    )
    LOGIN_LOCKOUT_AFTER: int = Field(
        default=5,
        description="Account lockout after N failed attempts"
    )
    LOGIN_LOCKOUT_MINUTES: int = Field(
        default=15,
        description="Lockout duration in minutes"
    )
    
    # Stripe Billing
    STRIPE_SECRET_KEY: str = Field(
        default="",
        description="Stripe secret key for payment processing"
    )
    STRIPE_WEBHOOK_SECRET: str = Field(
        default="",
        description="Stripe webhook secret for signature verification"
    )
    STRIPE_PRICE_ID_STARTER: str = Field(
        default="",
        description="Stripe price ID for Starter plan"
    )
    STRIPE_PRICE_ID_GROWTH: str = Field(
        default="",
        description="Stripe price ID for Growth plan"
    )
    STRIPE_PRICE_ID_ENTERPRISE: str = Field(
        default="",
        description="Stripe price ID for Enterprise plan"
    )
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="Google OAuth client ID"
    )
    GOOGLE_CLIENT_SECRET: str = Field(
        default="",
        description="Google OAuth client secret"
    )
    GOOGLE_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/v1/auth/google/callback",
        description="Google OAuth redirect URI"
    )
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend URL for OAuth redirects"
    )

    # CSRF (enabled in production; set CSRF_PROTECTION_ENABLED=true for staging)
    CSRF_PROTECTION_ENABLED: bool = Field(
        default=False,
        description="Enable CSRF validation for cookie-authenticated requests.",
    )

    # hCaptcha (CAPTCHA verification)
    HCAPTCHA_SECRET_KEY: str = Field(
        default="",
        description="hCaptcha secret key for server-side verification. Required when CAPTCHA is enforced. For local dev with test keys use 0x0000000000000000000000000000000000000000"
    )
    HCAPTCHA_SITE_KEY: str = Field(
        default="",
        description="hCaptcha site key (public) for frontend widget. Expose via NEXT_PUBLIC_HCAPTCHA_SITE_KEY."
    )

    # Auth cookie settings
    AUTH_COOKIE_NAME: str = Field(
        default="heliox_session",
        description="Name of the httpOnly auth cookie"
    )
    AUTH_COOKIE_MAX_AGE: int = Field(
        default=60 * 60 * 24 * 7,  # 7 days in seconds
        description="Auth cookie max age in seconds"
    )
    AUTH_COOKIE_SECURE: bool = Field(
        default=False,
        description="Set Secure flag (True in production over HTTPS)"
    )
    
    # Observability
    SENTRY_DSN: str = Field(
        default="",
        description="Sentry DSN for error monitoring. Empty = disabled."
    )
    SENTRY_ENVIRONMENT: str = Field(
        default="",
        description="Sentry environment (defaults to ENV if empty)"
    )
    OTEL_ENABLED: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing"
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(
        default="http://localhost:4317",
        description="OTLP exporter endpoint (Jaeger, etc.)"
    )
    LOG_JSON_FORMAT: bool = Field(
        default=True,
        description="Use JSON format for logs (structured logging)"
    )

    # Feature flags (JSON or comma-separated key=value)
    FEATURE_FLAGS: str = Field(
        default="",
        description="Feature flags JSON or key=value pairs. Empty = all enabled."
    )

    # Slack Notifications
    SLACK_WEBHOOK_URL: str = Field(
        default="",
        description="Slack Incoming Webhook URL for alerts"
    )
    
    # Scheduling
    DAILY_SUMMARY_HOUR: int = Field(
        default=9,
        ge=0,
        le=23,
        description="Hour (0-23) to send daily summary (default: 9 AM)"
    )
    TIMEZONE: str = Field(
        default="UTC",
        description="Timezone for scheduled tasks (e.g., 'America/New_York', 'UTC')"
    )
    
    # Plugins
    HELIOX_PLUGINS: List[str] = Field(
        default=[],
        description="Comma-separated module paths for plugins to load"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper
    
    @field_validator("ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        """Validate environment is one of the expected values."""
        valid_envs = ["dev", "staging", "production"]
        v_lower = v.lower()
        if v_lower not in valid_envs:
            raise ValueError(f"ENV must be one of {valid_envs}")
        return v_lower
    
    @field_validator("HELIOX_PLUGINS", mode="before")
    @classmethod
    def parse_plugins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v
    
    def model_post_init(self, __context) -> None:
        """Validate production-required settings after initialization."""
        # Security: In production, secrets and CORS must be explicitly configured
        if self.ENV == "production":
            # Validate CORS_ORIGINS is set and doesn't include localhost
            if not self.CORS_ORIGINS:
                raise ValueError(
                    "CORS_ORIGINS must be explicitly set via environment variable in production. "
                    "Cannot be empty."
                )
            localhost_origins = [origin for origin in self.CORS_ORIGINS if "localhost" in origin.lower()]
            if localhost_origins:
                raise ValueError(
                    f"CORS_ORIGINS cannot include localhost origins in production: {localhost_origins}. "
                    "Use production domain names only."
                )

        # Tenant safety: if multi-tenant is disabled, require a single team ID
        if not self.MULTI_TENANT:
            if not self.SINGLE_TENANT_TEAM_ID:
                raise ValueError(
                    "SINGLE_TENANT_TEAM_ID must be set when MULTI_TENANT is false."
                )


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Using lru_cache ensures we only read environment variables once
    and reuse the same Settings instance throughout the application.
    """
    return Settings()

