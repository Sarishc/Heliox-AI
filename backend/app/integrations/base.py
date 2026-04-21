"""Base classes and exceptions for integrations."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IntegrationConfigError(ValueError):
    """
    Raised when integration configuration is invalid or incomplete.

    Every integration must raise this (not bare ValueError) so callers can
    distinguish config problems from runtime errors and surface them clearly
    in the UI without exposing unexpected tracebacks.
    """

    def __init__(self, message: str, provider: str = "", field: str = ""):
        super().__init__(message)
        self.provider = provider
        self.field = field


class IntegrationSyncError(Exception):
    """
    Raised when an integration sync or API call fails.

    Wraps provider-specific errors (ClientError, GoogleAPIError, HTTP 5xx)
    so callers always catch one type. Always includes: provider, operation
    that failed, and the original error for logging.
    """

    def __init__(
        self,
        message: str,
        provider: str = "",
        operation: str = "",
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.operation = operation
        self.original_error = original_error


class IntegrationProvider(str, Enum):
    """Supported integration providers."""

    AWS = "aws"
    GCP = "gcp"
    GCP_BILLING_BIGQUERY = "gcp_billing_bigquery"
    AZURE = "azure"
    STRIPE = "stripe"
    SSO_GOOGLE = "sso_google"
    SSO_OKTA = "sso_okta"
    SLACK = "slack"
    CUSTOM = "custom"


class IntegrationStatus(str, Enum):
    """Integration connection status."""

    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"
    PENDING = "pending"


class SyncStatus(str, Enum):
    """Sync run status."""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class IntegrationHealthStatus(str, Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class IntegrationBase(ABC):
    """
    Base class for all integrations.

    All integrations must inherit from this class and implement:
    - validate_config(): Validate configuration before saving
    - sync(): Perform data synchronization
    - health(): Check integration health (returns detailed dict)

    Non-abstract helpers available to all subclasses:
    - health_check(): Quick bool — wraps health() for health endpoints / "Test connection" UI
    - get_config_schema(): Builds JSON schema from config_schema_fields or field name lists
    - get_display_config(): Returns config with secrets masked
    """

    # Provider identifier (must be set by subclasses)
    provider: IntegrationProvider = IntegrationProvider.CUSTOM

    # Display name for the integration
    display_name: str = "Custom Integration"

    # Description of what this integration does
    description: str = ""

    # Simple field name lists (legacy — override config_schema_fields for richer schema)
    required_config_fields: List[str] = []
    optional_config_fields: List[str] = []

    # Rich field schema used by the frontend "Connect" form and registry.
    # Structure: { field_name: { type, description, required, secret, placeholder } }
    # If empty, get_config_schema() falls back to required/optional_config_fields.
    config_schema_fields: Dict[str, Any] = {}

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validate_config(config)

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate integration configuration.

        Raises:
            IntegrationConfigError: If configuration is missing required fields or is malformed.
            Must NOT log sensitive data (API keys, secrets, etc).
        """
        pass

    @abstractmethod
    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Perform data synchronization.

        Returns:
            { "records_fetched": int, "records_saved": int, "records_skipped": int, "errors": [] }

        Raises:
            IntegrationSyncError: On critical failure. Partial failures are recorded in "errors".
        """
        pass

    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """
        Check integration health.

        Must never raise — catch all exceptions internally and return an unhealthy dict.

        Returns:
            {
                "status": "healthy|degraded|unhealthy",
                "message": "...",
                "details": { "api_reachable": bool, "credentials_valid": bool, ... }
            }
        """
        pass

    async def health_check(self) -> bool:
        """
        Quick health check — returns True if healthy, False otherwise.

        Used by the /health endpoint and the frontend "Test connection" button.
        Never raises — wraps health() which must also never raise.
        """
        try:
            result = await self.health()
            return result.get("status") == IntegrationHealthStatus.HEALTHY.value
        except Exception as e:
            logger.error("health_check() raised unexpectedly for %s: %s", self.provider, e)
            return False

    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get JSON schema for the integration's configuration form.

        Uses config_schema_fields (rich) if defined, otherwise falls back to
        required_config_fields / optional_config_fields (legacy field-name lists).
        """
        if self.config_schema_fields:
            properties = {}
            required = []
            for field_name, meta in self.config_schema_fields.items():
                prop: Dict[str, Any] = {"type": meta.get("type", "string")}
                if "description" in meta:
                    prop["description"] = meta["description"]
                if "placeholder" in meta:
                    prop["x-placeholder"] = meta["placeholder"]
                if meta.get("secret"):
                    prop["x-secret"] = True
                properties[field_name] = prop
                if meta.get("required", False):
                    required.append(field_name)
            return {"type": "object", "properties": properties, "required": required}

        # Legacy fallback
        properties = {}
        required = []
        for field in self.required_config_fields:
            properties[field] = {"type": "string"}
            required.append(field)
        for field in self.optional_config_fields:
            properties[field] = {"type": "string"}
        return {"type": "object", "properties": properties, "required": required}

    def get_display_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Return config with secret fields masked."""
        safe_config = config.copy()
        sensitive_patterns = [
            "key",
            "secret",
            "token",
            "password",
            "credential",
            "api_key",
            "access_key",
            "private_key",
        ]
        for key in safe_config:
            if any(p in key.lower() for p in sensitive_patterns):
                safe_config[key] = "***REDACTED***"
        return safe_config

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider.value}>"
