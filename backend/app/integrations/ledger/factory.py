"""Build a ledger adapter from a connection's decrypted configuration. Real clients are created lazily."""

from __future__ import annotations

import json
import time
from typing import Any, Mapping, Sequence

import httpx

from app.integrations.ledger.aws import AwsCostExplorerAdapter
from app.integrations.ledger.azure import AzureCostManagementAdapter
from app.integrations.ledger.base import AdapterConfigError, LedgerAdapter
from app.integrations.ledger.gcp import GcpBillingExportAdapter


def build_adapter(provider: str, config: Mapping[str, Any]) -> LedgerAdapter:
    """Credentials stay in the closures below; they are never placed on a stream, a run or a log line."""
    if provider == "aws":
        return AwsCostExplorerAdapter(config, client_factory=_aws_clients(config))
    if provider == "gcp_billing_bigquery":
        return GcpBillingExportAdapter(config, client_factory=_bigquery_client(config), parameters=_bigquery_parameters)
    if provider == "azure":
        return AzureCostManagementAdapter(
            config,
            http=httpx.Client(timeout=60.0, follow_redirects=False),
            token_provider=_azure_tokens(config),
            sleep=time.sleep,
        )
    raise AdapterConfigError("unsupported_provider")


def _aws_clients(config: Mapping[str, Any]):
    def factory(service: str) -> Any:
        import boto3  # type: ignore[import-untyped]

        return boto3.Session(
            aws_access_key_id=config.get("aws_access_key_id"),
            aws_secret_access_key=config.get("aws_secret_access_key"),
            region_name=config.get("aws_region", "us-east-1"),
        ).client(service)

    return factory


def _bigquery_client(config: Mapping[str, Any]):
    def factory() -> Any:
        from google.cloud import bigquery
        from google.oauth2 import service_account

        info = json.loads(str(config.get("service_account_json") or "{}"))
        credentials = service_account.Credentials.from_service_account_info(info)
        return bigquery.Client(credentials=credentials, project=str(config.get("gcp_project_id")))

    return factory


def _bigquery_parameters(values: Sequence[tuple[str, str, Any]]) -> Any:
    from google.cloud import bigquery

    return bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter(name, kind, value) for name, kind, value in values]
    )


def _azure_tokens(config: Mapping[str, Any]):
    def provider(_force_refresh: bool) -> str:
        from azure.identity import ClientSecretCredential

        credential = ClientSecretCredential(
            tenant_id=str(config.get("azure_tenant_id")),
            client_id=str(config.get("azure_client_id")),
            client_secret=str(config.get("azure_client_secret")),
        )
        return credential.get_token("https://management.azure.com/.default").token

    return provider
