"""Tests for Azure Cost Management integration."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.base import IntegrationProvider
from app.integrations.encryption import get_encryption
from app.integrations.models import IntegrationConnection, IntegrationSyncRun
from app.integrations.providers.azure_cost_management import (
    AzureCostManagementIntegration,
    _map_azure_service_to_gpu_type,
)
from app.integrations.registry import integration_registry
from app.models.cost import CostSnapshot
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User


def test_azure_provider_registered():
    """Azure provider is registered in the integration registry."""
    assert integration_registry.get(IntegrationProvider.AZURE) is AzureCostManagementIntegration


def test_azure_validate_config_empty_allowed():
    """Empty config is allowed for schema discovery."""
    integration = AzureCostManagementIntegration({})
    assert integration.provider == IntegrationProvider.AZURE


def test_azure_validate_config_missing_required():
    """Missing required fields raise ValueError."""
    with pytest.raises(ValueError, match="Missing required field"):
        AzureCostManagementIntegration({"azure_tenant_id": "x"})


def test_azure_validate_config_invalid_subscription():
    """Invalid subscription ID format raises ValueError."""
    with pytest.raises(ValueError, match="subscription_ids"):
        AzureCostManagementIntegration({
            "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "azure_client_secret": "a" * 40,
            "subscription_ids": [],
        })


def test_azure_validate_config_valid():
    """Valid config passes validation."""
    config = {
        "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_secret": "a" * 40,
        "subscription_ids": ["ffffffff-0000-1111-2222-333333333333"],
    }
    integration = AzureCostManagementIntegration(config)
    assert integration.subscription_ids == ["ffffffff-0000-1111-2222-333333333333"]


def test_azure_validate_config_subscription_ids_string():
    """subscription_ids as comma-separated string is parsed."""
    config = {
        "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_secret": "a" * 40,
        "subscription_ids": "aaaaaaaa-0000-0000-0000-000000000001, bbbbbbbb-0000-0000-0000-000000000002",
    }
    integration = AzureCostManagementIntegration(config)
    assert len(integration.subscription_ids) == 2


def test_map_azure_service_to_gpu_type():
    """Service name maps to correct GPU type."""
    assert _map_azure_service_to_gpu_type("Virtual Machines") == "azure_vm"
    assert _map_azure_service_to_gpu_type("Azure Machine Learning") == "azure_ml"
    assert _map_azure_service_to_gpu_type("Container Service") == "azure_aks"
    assert _map_azure_service_to_gpu_type("Azure Batch") == "azure_batch"
    assert _map_azure_service_to_gpu_type("Storage") == "azure_other"
    assert _map_azure_service_to_gpu_type("") == "azure_other"


@pytest.mark.asyncio
async def test_azure_health_success():
    """Health check returns healthy when API succeeds."""
    config = {
        "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_secret": "a" * 40,
        "subscription_ids": ["ffffffff-0000-1111-2222-333333333333"],
    }

    with patch(
        "app.integrations.providers.azure_cost_management._get_access_token",
        return_value="mock-token",
    ):
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"properties": {"rows": [], "columns": []}}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )

            integration = AzureCostManagementIntegration(config)
            result = await integration.health()

    assert result["status"] == "healthy"
    assert result["details"]["credentials_valid"] is True


@pytest.mark.asyncio
async def test_azure_health_401_unauthorized():
    """Health check returns unhealthy on 401."""
    config = {
        "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_secret": "a" * 40,
        "subscription_ids": ["ffffffff-0000-1111-2222-333333333333"],
    }

    with patch(
        "app.integrations.providers.azure_cost_management._get_access_token",
        return_value="mock-token",
    ):
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )

            integration = AzureCostManagementIntegration(config)
            result = await integration.health()

    assert result["status"] == "unhealthy"
    assert "Invalid" in result["message"] or "credentials" in result["message"].lower()


def test_azure_get_display_config_masks_secrets():
    """Display config masks client secret."""
    config = {
        "azure_tenant_id": "tid",
        "azure_client_id": "cid",
        "azure_client_secret": "secret123",
        "subscription_ids": ["sub1"],
    }
    integration = AzureCostManagementIntegration(config)
    safe = integration.get_display_config(config)
    assert safe["azure_client_secret"] == "***REDACTED***"
    assert safe["azure_tenant_id"] == "tid"


def test_azure_connection_encryption(db_session):
    """Azure config is encrypted when stored."""
    team = Team(name="Test")
    user = User(email="a@b.com", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)

    config = {
        "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_secret": "my-secret-value",
        "subscription_ids": ["ffffffff-0000-1111-2222-333333333333"],
    }

    encryption = get_encryption()
    encrypted = encryption.encrypt_config(config)

    assert "my-secret-value" not in encrypted
    assert encrypted != config

    decrypted = encryption.decrypt_config(encrypted)
    assert decrypted["azure_client_secret"] == "my-secret-value"
