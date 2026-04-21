"""Integration registry for managing available integrations."""

import logging
from typing import Dict, List, Optional, Type

from app.integrations.base import IntegrationBase, IntegrationProvider

logger = logging.getLogger(__name__)


class IntegrationRegistry:
    """
    Registry for managing available integrations.

    Integrations register themselves with the registry, which allows:
    - Discovery of available integrations
    - Instantiation of integrations by provider name
    - Listing integration metadata
    """

    def __init__(self):
        """Initialize empty registry."""
        self._integrations: Dict[IntegrationProvider, Type[IntegrationBase]] = {}

    def register(self, provider: IntegrationProvider, integration_class: Type[IntegrationBase]) -> None:
        """
        Register an integration.

        Args:
            provider: Provider identifier
            integration_class: Integration class (must inherit from IntegrationBase)

        Raises:
            ValueError: If provider already registered or class is invalid
        """
        if provider in self._integrations:
            raise ValueError(f"Integration for provider {provider.value} already registered")

        if not issubclass(integration_class, IntegrationBase):
            raise ValueError(
                f"Integration class must inherit from IntegrationBase, " f"got {integration_class.__name__}"
            )

        self._integrations[provider] = integration_class
        logger.info(f"Registered integration: {provider.value} ({integration_class.__name__})")

    def get(self, provider: IntegrationProvider) -> Optional[Type[IntegrationBase]]:
        """
        Get integration class by provider.

        Args:
            provider: Provider identifier

        Returns:
            Integration class or None if not found
        """
        return self._integrations.get(provider)

    def list_available(self) -> List[Dict[str, any]]:
        """
        List all available integrations.

        Returns:
            List of integration metadata dictionaries:
            [
                {
                    "provider": "aws",
                    "display_name": "AWS Cost Explorer",
                    "description": "Import costs from AWS Cost Explorer API",
                    "enabled": true,
                    "config_schema": {...}
                },
                ...
            ]
        """
        integrations = []

        for provider, integration_class in self._integrations.items():
            # Build schema from class-level field lists — no instantiation needed
            try:
                required = getattr(integration_class, "required_config_fields", [])
                optional = getattr(integration_class, "optional_config_fields", [])
                properties = {f: {"type": "string"} for f in required + optional}
                config_schema = {
                    "type": "object",
                    "properties": properties,
                    "required": list(required),
                }
                metadata = {
                    "provider": provider.value,
                    "display_name": getattr(integration_class, "display_name", provider.value),
                    "description": getattr(integration_class, "description", ""),
                    "enabled": True,
                    "config_schema": config_schema,
                }
                integrations.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to get metadata for {provider.value}: {e}")

        # Add disabled integrations (not yet implemented)
        for provider in IntegrationProvider:
            if provider not in self._integrations:
                integrations.append(
                    {
                        "provider": provider.value,
                        "display_name": provider.value.upper(),
                        "description": f"{provider.value.upper()} integration (coming soon)",
                        "enabled": False,
                        "config_schema": None,
                    }
                )

        return integrations

    def is_registered(self, provider) -> bool:
        """
        Check if provider is registered.

        Accepts either an IntegrationProvider enum or a plain string value.
        """
        if isinstance(provider, str):
            try:
                provider = IntegrationProvider(provider)
            except ValueError:
                return False
        return provider in self._integrations


# Global registry instance
integration_registry = IntegrationRegistry()
