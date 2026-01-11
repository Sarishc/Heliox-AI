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
    
    # Security - REQUIRED: No defaults for production safety
    SECRET_KEY: str = Field(
        description="Secret key for JWT token encoding (REQUIRED - set via environment variable)"
    )
    
    ADMIN_API_KEY: str = Field(
        description="API key for admin endpoints (REQUIRED - set via environment variable)"
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


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Using lru_cache ensures we only read environment variables once
    and reuse the same Settings instance throughout the application.
    """
    return Settings()

