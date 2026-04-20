"""
End-to-end tests for cloud cost integrations (AWS, GCP, Azure).

These tests verify that:
  1. The real integration classes return cost records when given mocked API responses.
  2. The dead plugins layer is gone — importing it raises ModuleNotFoundError.
  3. All three providers are registered in the integration_registry.
  4. The /plugins route returns the real integrations catalog, not stub names.
  5. validate_config() raises IntegrationConfigError on missing required fields.
  6. health_check() returns bool (never raises) for healthy and unreachable APIs.
  7. Azure 429 respects Retry-After; Azure 401 refreshes token exactly once.
  8. All three providers raise IntegrationSyncError (not raw exceptions) on API failure.

Cloud SDKs (boto3, google-cloud-bigquery, azure-identity) are mocked so these
tests run without real credentials and work in CI.
"""
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_SA_JSON = json.dumps({
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "billing@test-project.iam.gserviceaccount.com",
    "client_id": "123456",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
})

AWS_CONFIG = {
    "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "aws_region": "us-east-1",
}

GCP_CONFIG = {
    "gcp_project_id": "test-project",
    "bigquery_dataset": "billing_export",
    "service_account_json": VALID_SA_JSON,
}

AZURE_CONFIG = {
    "azure_tenant_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "azure_client_secret": "a" * 40,
    "subscription_ids": ["ffffffff-0000-1111-2222-333333333333"],
}


def _mock_db_with_team(team_id: uuid.UUID):
    """Return a MagicMock Session that looks like it has one team row."""
    db = MagicMock()
    mock_team = MagicMock()
    mock_team.id = team_id
    # query(Team).filter(...).first() → mock_team
    db.query.return_value.filter.return_value.first.return_value = mock_team
    # query(CostSnapshot).filter(...).first() → None (no existing row → creates new)
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    return db


# ── Regression: dead plugins layer must be gone ───────────────────────────────

def test_plugins_module_does_not_exist():
    """
    Importing app.plugins raises ModuleNotFoundError.

    This is the definitive regression check: it guarantees the dead layer can
    never silently come back and shadow the real integrations.
    """
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.plugins")


def test_plugins_registry_does_not_exist():
    """The old plugin registry sub-module is gone."""
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.plugins.registry")


# ── Integration registry ──────────────────────────────────────────────────────

def test_all_three_providers_registered():
    """AWS, GCP BigQuery, and Azure are registered in the real integration_registry."""
    import app.integrations.providers  # noqa: F401 — registers providers
    from app.integrations.registry import integration_registry
    from app.integrations.base import IntegrationProvider

    assert integration_registry.get(IntegrationProvider.AWS) is not None
    assert integration_registry.get(IntegrationProvider.GCP_BILLING_BIGQUERY) is not None
    assert integration_registry.get(IntegrationProvider.AZURE) is not None


def test_list_available_returns_real_integrations():
    """integration_registry.list_available() includes all real providers as enabled."""
    import app.integrations.providers  # noqa: F401
    from app.integrations.registry import integration_registry

    available = integration_registry.list_available()
    providers = {entry["provider"] for entry in available}
    assert "aws" in providers
    assert "gcp_billing_bigquery" in providers
    assert "azure" in providers

    enabled = {e["provider"] for e in available if e["enabled"]}
    assert "aws" in enabled
    assert "gcp_billing_bigquery" in enabled
    assert "azure" in enabled


# ── AWS Cost Explorer sync ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aws_sync_returns_saved_records():
    """
    AWS Cost Explorer sync processes mocked API response and reports records_saved > 0.

    Fixture represents one day of EC2 costs split across two groups.
    """
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    ce_response = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-04-01", "End": "2026-04-02"},
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute", "111122223333"],
                        "Metrics": {"UnblendedCost": {"Amount": "125.50", "Unit": "USD"}},
                    },
                    {
                        "Keys": ["Amazon SageMaker", "111122223333"],
                        "Metrics": {"UnblendedCost": {"Amount": "42.00", "Unit": "USD"}},
                    },
                ],
            }
        ]
    }

    integration = AWSCostExplorerIntegration(AWS_CONFIG)

    with patch(
        "app.integrations.providers.aws_cost_explorer.get_db",
        return_value=iter([mock_db]),
    ):
        mock_boto3_session = MagicMock()
        mock_ce_client = MagicMock()
        mock_boto3_session.client.return_value = mock_ce_client
        mock_ce_client.get_cost_and_usage.return_value = ce_response

        with patch(
            "app.integrations.providers.aws_cost_explorer.boto3.Session",
            return_value=mock_boto3_session,
        ):
            result = await integration.sync(team_id=str(team_id))

    assert result["records_fetched"] == 2
    assert result["records_saved"] == 2
    assert result["records_skipped"] == 0


@pytest.mark.asyncio
async def test_aws_sync_skips_zero_cost_rows():
    """Zero-cost rows in the CE response are counted as skipped, not saved."""
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    ce_response = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-04-01", "End": "2026-04-02"},
                "Groups": [
                    {
                        "Keys": ["Amazon S3", "111122223333"],
                        "Metrics": {"UnblendedCost": {"Amount": "0", "Unit": "USD"}},
                    }
                ],
            }
        ]
    }

    integration = AWSCostExplorerIntegration(AWS_CONFIG)

    with patch(
        "app.integrations.providers.aws_cost_explorer.get_db",
        return_value=iter([mock_db]),
    ):
        mock_boto3_session = MagicMock()
        mock_ce_client = MagicMock()
        mock_boto3_session.client.return_value = mock_ce_client
        mock_ce_client.get_cost_and_usage.return_value = ce_response

        with patch(
            "app.integrations.providers.aws_cost_explorer.boto3.Session",
            return_value=mock_boto3_session,
        ):
            result = await integration.sync(team_id=str(team_id))

    assert result["records_saved"] == 0
    assert result["records_skipped"] == 1


# ── GCP BigQuery sync ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gcp_sync_returns_saved_records():
    """
    GCP BigQuery billing sync processes mocked query results and saves records.

    Fixture represents two rows from a billing export query.
    """
    from app.integrations.providers.gcp_billing_bigquery import GCPBillingBigQueryIntegration

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    # Mock BigQuery row objects
    row1 = MagicMock()
    row1.usage_date = date(2026, 4, 1)
    row1.service_name = "Compute Engine"
    row1.project_id = "test-project"
    row1.total_cost = Decimal("200.00")
    # label attribute doesn't exist on this row (no label grouping)

    row2 = MagicMock()
    row2.usage_date = date(2026, 4, 2)
    row2.service_name = "Vertex AI"
    row2.project_id = "test-project"
    row2.total_cost = Decimal("75.50")

    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [row1, row2]

    mock_bq_client = MagicMock()
    mock_bq_client.query.return_value = mock_query_job

    integration = GCPBillingBigQueryIntegration(GCP_CONFIG)

    with patch(
        "app.integrations.providers.gcp_billing_bigquery.get_db",
        return_value=iter([mock_db]),
    ):
        with patch.object(integration, "_get_bigquery_client", return_value=mock_bq_client):
            result = await integration.sync(team_id=str(team_id))

    assert result["records_fetched"] == 2
    assert result["records_saved"] == 2


# ── Azure Cost Management sync ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_azure_sync_returns_saved_records():
    """
    Azure Cost Management sync processes mocked API response and saves records.

    Fixture matches the real Azure Cost Management query response schema.
    """
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    # Azure returns columnar data matching the query grouping order:
    # grouping: [ServiceName, Date] + aggregation: Cost → rows: [service, date, cost]
    azure_response = {
        "properties": {
            "columns": [
                {"name": "ServiceName", "type": "String"},
                {"name": "UsageDate", "type": "Number"},
                {"name": "Cost", "type": "Number"},
            ],
            "rows": [
                ["Virtual Machines", 20260401, 125.50],
                ["Azure Machine Learning", 20260401, 42.00],
                ["Storage", 20260401, 0.0],  # zero-cost row → skipped
            ],
        }
    }

    integration = AzureCostManagementIntegration(AZURE_CONFIG)

    with patch(
        "app.integrations.providers.azure_cost_management.get_db",
        return_value=iter([mock_db]),
    ):
        with patch(
            "app.integrations.providers.azure_cost_management._get_access_token",
            return_value="mock-bearer-token",
        ):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = azure_response

            with patch("httpx.AsyncClient") as mock_httpx:
                mock_httpx.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_resp
                )
                result = await integration.sync(team_id=str(team_id))

    assert result["records_saved"] >= 2  # 2 non-zero rows
    assert result["records_skipped"] >= 1  # zero-cost row


# ── /plugins route now returns real integration catalog ───────────────────────

def test_get_plugins_route_returns_integrations_catalog():
    """GET /api/v1/plugins returns the real integration catalog, not stub plugin names."""
    import uuid as _uuid
    from unittest.mock import MagicMock, patch
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.security import get_team_api_key_optional
    from app.auth.deps import get_current_user_optional

    # Mock a valid TeamAPIKey so auth passes without a real DB
    mock_api_key = MagicMock()
    mock_api_key.team_id = _uuid.uuid4()

    # Mock Redis so rate limiter doesn't 503 in the test environment
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True
    mock_redis.ping.return_value = True

    app.dependency_overrides[get_team_api_key_optional] = lambda: mock_api_key
    app.dependency_overrides[get_current_user_optional] = lambda: None
    try:
        with patch("app.core.cache.get_redis", return_value=mock_redis), \
             patch("app.core.rate_limit.require_redis", return_value=mock_redis):
            client = TestClient(app)
            response = client.get("/api/v1/plugins")
            assert response.status_code == 200
            body = response.json()

            # Response must use 'integrations' key (not old 'plugins' list of strings)
            assert "integrations" in body
            providers = {entry["provider"] for entry in body["integrations"]}
            assert "aws" in providers
            assert "gcp_billing_bigquery" in providers
            assert "azure" in providers

            # Every enabled entry must have a config_schema
            for entry in body["integrations"]:
                if entry.get("enabled"):
                    assert entry.get("config_schema") is not None
    finally:
        app.dependency_overrides.pop(get_team_api_key_optional, None)
        app.dependency_overrides.pop(get_current_user_optional, None)


# ── Step 6: validate_config() raises IntegrationConfigError ──────────────────

def test_aws_validate_config_raises_on_missing_key():
    """AWS validate_config raises IntegrationConfigError when aws_access_key_id is absent."""
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration
    from app.integrations.base import IntegrationConfigError

    bad_config = {"aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"}
    with pytest.raises(IntegrationConfigError) as exc_info:
        AWSCostExplorerIntegration(bad_config)
    assert exc_info.value.field == "aws_access_key_id"
    assert exc_info.value.provider == "aws"


def test_gcp_validate_config_raises_on_missing_project():
    """GCP validate_config raises IntegrationConfigError when gcp_project_id is absent."""
    from app.integrations.providers.gcp_billing_bigquery import GCPBillingBigQueryIntegration
    from app.integrations.base import IntegrationConfigError

    bad_config = {
        "bigquery_dataset": "billing_export",
        "service_account_json": VALID_SA_JSON,
    }
    with pytest.raises(IntegrationConfigError) as exc_info:
        GCPBillingBigQueryIntegration(bad_config)
    assert exc_info.value.field == "gcp_project_id"
    assert exc_info.value.provider == "gcp_billing_bigquery"


def test_azure_validate_config_raises_on_missing_tenant():
    """Azure validate_config raises IntegrationConfigError when azure_tenant_id is absent."""
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration
    from app.integrations.base import IntegrationConfigError

    bad_config = {
        "azure_client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "azure_client_secret": "a" * 40,
        "subscription_ids": ["ffffffff-0000-1111-2222-333333333333"],
    }
    with pytest.raises(IntegrationConfigError) as exc_info:
        AzureCostManagementIntegration(bad_config)
    assert exc_info.value.field == "azure_tenant_id"
    assert exc_info.value.provider == "azure"


def test_azure_validate_config_rejects_empty_config():
    """Azure validate_config raises IntegrationConfigError for empty config (no silent bypass)."""
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration
    from app.integrations.base import IntegrationConfigError

    with pytest.raises(IntegrationConfigError):
        AzureCostManagementIntegration({})


# ── Step 6: health_check() returns bool, never raises ────────────────────────

@pytest.mark.asyncio
async def test_aws_health_check_returns_true_when_healthy():
    """health_check() returns True when AWS credentials are valid."""
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration

    integration = AWSCostExplorerIntegration(AWS_CONFIG)
    with patch.object(integration, "health", return_value={
        "status": "healthy",
        "message": "AWS Cost Explorer connection successful",
        "details": {},
    }):
        assert await integration.health_check() is True


@pytest.mark.asyncio
async def test_gcp_health_check_returns_true_when_healthy():
    """health_check() returns True when GCP BigQuery is reachable."""
    from app.integrations.providers.gcp_billing_bigquery import GCPBillingBigQueryIntegration

    integration = GCPBillingBigQueryIntegration(GCP_CONFIG)
    with patch.object(integration, "health", return_value={
        "status": "healthy",
        "message": "GCP BigQuery billing connection successful",
        "details": {},
    }):
        assert await integration.health_check() is True


@pytest.mark.asyncio
async def test_azure_health_check_returns_true_when_healthy():
    """health_check() returns True when Azure Cost Management is reachable."""
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration

    integration = AzureCostManagementIntegration(AZURE_CONFIG)
    with patch.object(integration, "health", return_value={
        "status": "healthy",
        "message": "Azure Cost Management connection successful",
        "details": {},
    }):
        assert await integration.health_check() is True


@pytest.mark.asyncio
async def test_aws_health_check_returns_false_when_unreachable():
    """health_check() returns False (never raises) when AWS API is unreachable."""
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration
    from botocore.exceptions import BotoCoreError

    integration = AWSCostExplorerIntegration(AWS_CONFIG)
    with patch.object(integration, "_get_caller_identity", side_effect=ConnectionError("refused")):
        result = await integration.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_gcp_health_check_returns_false_when_unreachable():
    """health_check() returns False (never raises) when GCP API is unreachable."""
    from app.integrations.providers.gcp_billing_bigquery import GCPBillingBigQueryIntegration

    integration = GCPBillingBigQueryIntegration(GCP_CONFIG)
    with patch.object(integration, "_get_bigquery_client", side_effect=ConnectionError("refused")):
        result = await integration.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_azure_health_check_returns_false_when_unreachable():
    """health_check() returns False (never raises) when Azure API is unreachable."""
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration

    integration = AzureCostManagementIntegration(AZURE_CONFIG)
    with patch.object(integration, "_get_token", side_effect=ConnectionError("refused")):
        result = await integration.health_check()
    assert result is False


# ── Step 6: Azure 429 and 401 retry logic ────────────────────────────────────

@pytest.mark.asyncio
async def test_azure_429_sleeps_retry_after_and_retries():
    """
    _query_subscription() sleeps for the Retry-After header value then retries once.

    Verifies that asyncio.sleep is called with the correct delay extracted from
    the 429 response headers.
    """
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration
    from datetime import date

    integration = AzureCostManagementIntegration(AZURE_CONFIG)

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {"Retry-After": "10"}

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"properties": {"rows": [], "columns": []}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_429, mock_200])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await integration._query_subscription(
            mock_client,
            sub_id=AZURE_CONFIG["subscription_ids"][0],
            token="test-token",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 20),
        )

    mock_sleep.assert_called_once_with(10)
    assert mock_client.post.call_count == 2
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_azure_429_caps_retry_after_at_max():
    """Retry-After values above _MAX_RETRY_AFTER_SECONDS are capped, not passed directly."""
    from app.integrations.providers.azure_cost_management import (
        AzureCostManagementIntegration,
        _MAX_RETRY_AFTER_SECONDS,
    )
    from datetime import date

    integration = AzureCostManagementIntegration(AZURE_CONFIG)

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {"Retry-After": "9999"}  # well above cap

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"properties": {"rows": [], "columns": []}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_429, mock_200])

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await integration._query_subscription(
            mock_client,
            sub_id=AZURE_CONFIG["subscription_ids"][0],
            token="test-token",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 20),
        )

    mock_sleep.assert_called_once_with(_MAX_RETRY_AFTER_SECONDS)


@pytest.mark.asyncio
async def test_azure_401_refreshes_token_and_retries_exactly_once():
    """
    _query_subscription() refreshes the token on 401 and retries exactly once.

    Verifies that _get_token() is called once (the refresh) and that the
    second POST uses the fresh token in its Authorization header.
    """
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration
    from datetime import date

    integration = AzureCostManagementIntegration(AZURE_CONFIG)

    mock_401 = MagicMock()
    mock_401.status_code = 401
    mock_401.headers = {}

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"properties": {"rows": [], "columns": []}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_401, mock_200])

    with patch.object(integration, "_get_token", return_value="fresh-token") as mock_get_token:
        result = await integration._query_subscription(
            mock_client,
            sub_id=AZURE_CONFIG["subscription_ids"][0],
            token="expired-token",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 20),
        )

    mock_get_token.assert_called_once()
    assert mock_client.post.call_count == 2
    # Second call must use the refreshed token
    _, second_kwargs = mock_client.post.call_args
    assert second_kwargs["headers"]["Authorization"] == "Bearer fresh-token"
    assert result.status_code == 200


# ── Step 6: IntegrationSyncError raised on API failure ───────────────────────

@pytest.mark.asyncio
async def test_aws_sync_raises_integration_sync_error_on_api_failure():
    """AWS sync raises IntegrationSyncError (not ClientError) when Cost Explorer returns an error."""
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration
    from app.integrations.base import IntegrationSyncError
    from botocore.exceptions import ClientError

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    integration = AWSCostExplorerIntegration(AWS_CONFIG)

    client_error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
        "GetCostAndUsage",
    )

    with patch("app.integrations.providers.aws_cost_explorer.get_db", return_value=iter([mock_db])):
        mock_boto3_session = MagicMock()
        mock_ce_client = MagicMock()
        mock_boto3_session.client.return_value = mock_ce_client
        mock_ce_client.get_cost_and_usage.side_effect = client_error

        with patch("app.integrations.providers.aws_cost_explorer.boto3.Session", return_value=mock_boto3_session):
            with pytest.raises(IntegrationSyncError) as exc_info:
                await integration.sync(team_id=str(team_id))

    assert exc_info.value.provider == "aws"
    assert exc_info.value.operation == "sync"
    assert isinstance(exc_info.value.original_error, ClientError)


@pytest.mark.asyncio
async def test_gcp_sync_raises_integration_sync_error_on_api_failure():
    """GCP sync raises IntegrationSyncError (not GoogleAPIError) when BigQuery fails."""
    from app.integrations.providers.gcp_billing_bigquery import GCPBillingBigQueryIntegration
    from app.integrations.base import IntegrationSyncError
    from google.api_core.exceptions import GoogleAPIError

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    integration = GCPBillingBigQueryIntegration(GCP_CONFIG)

    gcp_error = GoogleAPIError("Quota exceeded")

    with patch("app.integrations.providers.gcp_billing_bigquery.get_db", return_value=iter([mock_db])):
        mock_bq_client = MagicMock()
        mock_bq_client.query.side_effect = gcp_error

        with patch.object(integration, "_get_bigquery_client", return_value=mock_bq_client):
            with pytest.raises(IntegrationSyncError) as exc_info:
                await integration.sync(team_id=str(team_id))

    assert exc_info.value.provider == "gcp_billing_bigquery"
    assert exc_info.value.operation == "sync"
    assert isinstance(exc_info.value.original_error, GoogleAPIError)


@pytest.mark.asyncio
async def test_azure_sync_raises_integration_sync_error_on_token_failure():
    """Azure sync raises IntegrationSyncError when token acquisition fails."""
    from app.integrations.providers.azure_cost_management import AzureCostManagementIntegration
    from app.integrations.base import IntegrationSyncError

    team_id = uuid.uuid4()
    mock_db = _mock_db_with_team(team_id)

    integration = AzureCostManagementIntegration(AZURE_CONFIG)

    with patch("app.integrations.providers.azure_cost_management.get_db", return_value=iter([mock_db])):
        with patch.object(integration, "_get_token", side_effect=RuntimeError("auth service down")):
            with pytest.raises(IntegrationSyncError) as exc_info:
                await integration.sync(team_id=str(team_id))

    assert exc_info.value.provider == "azure"
    assert exc_info.value.operation == "sync"
    assert isinstance(exc_info.value.original_error, RuntimeError)
