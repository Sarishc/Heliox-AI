"""Base classes for integrations."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IntegrationProvider(str, Enum):
    """Supported integration providers."""
    AWS = "aws"
    GCP = "gcp"
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
    - health(): Check integration health
    """
    
    # Provider identifier (must be set by subclasses)
    provider: IntegrationProvider = IntegrationProvider.CUSTOM
    
    # Display name for the integration
    display_name: str = "Custom Integration"
    
    # Description of what this integration does
    description: str = ""
    
    # Required configuration fields
    required_config_fields: List[str] = []
    
    # Optional configuration fields
    optional_config_fields: List[str] = []
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize integration with configuration.
        
        Args:
            config: Dictionary containing integration configuration
        """
        self.config = config
        self.validate_config(config)
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate integration configuration.
        
        Should raise ValueError if configuration is invalid.
        Must NOT log sensitive data (API keys, secrets, etc).
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ValueError: If configuration is invalid
        """
        pass
    
    @abstractmethod
    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Perform data synchronization.
        
        This method should:
        1. Connect to the external service
        2. Fetch data since last_sync_at (or all data if None)
        3. Transform data to Heliox format
        4. Save to database
        5. Return metrics about what was synced
        
        Args:
            team_id: Team ID to sync data for
            last_sync_at: Last successful sync timestamp (None for first sync)
            
        Returns:
            Dictionary with sync metrics:
            {
                "records_fetched": 100,
                "records_saved": 95,
                "records_skipped": 5,
                "errors": []
            }
            
        Raises:
            Exception: If sync fails critically
        """
        pass
    
    @abstractmethod
    async def health(self) -> Dict[str, Any]:
        """
        Check integration health.
        
        This method should:
        1. Test connection to external service
        2. Verify credentials are valid
        3. Check API rate limits if applicable
        4. Return health status and details
        
        Returns:
            Dictionary with health information:
            {
                "status": "healthy|degraded|unhealthy",
                "message": "Description of health status",
                "details": {
                    "api_reachable": true,
                    "credentials_valid": true,
                    "rate_limit_remaining": 5000
                }
            }
        """
        pass
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get JSON schema for configuration.
        
        Returns schema that can be used to validate config and generate UI forms.
        
        Returns:
            JSON schema dictionary
        """
        properties = {}
        required = []
        
        for field in self.required_config_fields:
            properties[field] = {"type": "string"}
            required.append(field)
        
        for field in self.optional_config_fields:
            properties[field] = {"type": "string"}
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    def get_display_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get safe version of config for display (masks sensitive fields).
        
        Args:
            config: Full configuration dictionary
            
        Returns:
            Config with sensitive fields masked
        """
        safe_config = config.copy()
        
        # Mask common sensitive field patterns
        sensitive_patterns = [
            "key", "secret", "token", "password", "credential",
            "api_key", "access_key", "private_key"
        ]
        
        for key in safe_config.keys():
            key_lower = key.lower()
            if any(pattern in key_lower for pattern in sensitive_patterns):
                safe_config[key] = "***REDACTED***"
        
        return safe_config
    
    def __repr__(self) -> str:
        """String representation."""
        return f"<{self.__class__.__name__} provider={self.provider.value}>"
