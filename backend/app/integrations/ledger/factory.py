"""Build a ledger adapter from a connection's decrypted configuration. Real clients are created lazily."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

import httpx

from app.integrations.ledger.aws import AwsCostExplorerAdapter
from app.integrations.ledger.azure import AzureCostManagementAdapter
from app.integrations.ledger.base import AdapterConfigError, LedgerAdapter, ScopeLookupDenied, ScopeLookupMissing
from app.integrations.ledger.gcp import PROJECT_RE, GcpBillingExportAdapter

REQUIRED_CREDENTIALS = {
    "aws": ("aws_access_key_id", "aws_secret_access_key"),
    "gcp_billing_bigquery": ("service_account_json",),
    "azure": ("azure_tenant_id", "azure_client_id", "azure_client_secret"),
}
BILLING_READ_SCOPE = "https://www.googleapis.com/auth/cloud-billing.readonly"


def _aws_session(config: Mapping[str, Any]) -> Any:
    import boto3  # type: ignore[import-untyped]

    return boto3.Session(
        aws_access_key_id=config.get("aws_access_key_id"),
        aws_secret_access_key=config.get("aws_secret_access_key"),
        region_name=config.get("aws_region", "us-east-1"),
    )


def _service_account(config: Mapping[str, Any], scopes: Sequence[str] = ()) -> Any:
    from google.oauth2 import service_account

    info = json.loads(str(config.get("service_account_json")))
    return service_account.Credentials.from_service_account_info(info, scopes=list(scopes) or None)


def _bigquery_client(config: Mapping[str, Any]) -> Any:
    from google.cloud import bigquery

    return bigquery.Client(credentials=_service_account(config), project=str(config.get("gcp_project_id")))


def _bigquery_parameters(values: Sequence[tuple[str, str, Any]]) -> Any:
    from google.cloud import bigquery

    return bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter(name, kind, value) for name, kind, value in values]
    )


def _billing_session(config: Mapping[str, Any]) -> Any:
    from google.auth.transport.requests import AuthorizedSession

    return AuthorizedSession(_service_account(config, [BILLING_READ_SCOPE]))


def _azure_credential(config: Mapping[str, Any]) -> Any:
    from azure.identity import ClientSecretCredential

    return ClientSecretCredential(
        tenant_id=str(config.get("azure_tenant_id")),
        client_id=str(config.get("azure_client_id")),
        client_secret=str(config.get("azure_client_secret")),
    )


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=60.0, follow_redirects=False)


@dataclass(frozen=True)
class ClientFactories:
    """Everything that reaches a provider. Tests replace these; nothing else creates a client."""

    aws_session: Callable[[Mapping[str, Any]], Any] = _aws_session
    bigquery_client: Callable[[Mapping[str, Any]], Any] = _bigquery_client
    bigquery_parameters: Callable[[Sequence[tuple[str, str, Any]]], Any] = _bigquery_parameters
    billing_session: Callable[[Mapping[str, Any]], Any] = _billing_session
    azure_credential: Callable[[Mapping[str, Any]], Any] = _azure_credential
    http_client: Callable[[], httpx.Client] = _http_client


def build_adapter(
    provider: str, config: Mapping[str, Any], clients: ClientFactories = ClientFactories()
) -> LedgerAdapter:
    """Credentials stay in the closures below; they are never placed on a stream, a run or a log line."""
    required = REQUIRED_CREDENTIALS.get(provider)
    if required is None:
        raise AdapterConfigError("unsupported_provider")
    if not all(config.get(name) for name in required):
        raise AdapterConfigError("missing_credentials")
    if provider == "aws":
        return AwsCostExplorerAdapter(
            config, client_factory=lambda service: clients.aws_session(config).client(service)
        )
    if provider == "gcp_billing_bigquery":
        try:
            parsed = json.loads(str(config["service_account_json"]))
        except ValueError:
            raise AdapterConfigError("invalid_credentials", "service_account_json is not JSON") from None
        if not isinstance(parsed, Mapping):
            raise AdapterConfigError("invalid_credentials", "service_account_json is not an object")
        return GcpBillingExportAdapter(
            config,
            client_factory=lambda: clients.bigquery_client(config),
            parameters=clients.bigquery_parameters,
            project_billing_info=_project_billing_lookup(lambda: clients.billing_session(config)),
        )
    return AzureCostManagementAdapter(
        config,
        http=clients.http_client(),
        token_provider=_azure_tokens(lambda: clients.azure_credential(config)),
        sleep=time.sleep,
    )


def _project_billing_lookup(session: Callable[[], Any]) -> Callable[[str], Mapping[str, Any]]:
    """Cloud Billing projects.getBillingInfo. Needs resourcemanager.projects.get on the project."""

    def lookup(project: str) -> Mapping[str, Any]:
        if not PROJECT_RE.match(project):
            raise ScopeLookupMissing()
        response = session().get(f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo", timeout=30)
        if response.status_code == 403:
            raise ScopeLookupDenied()
        if response.status_code == 404:
            raise ScopeLookupMissing()
        if response.status_code != 200:
            raise RuntimeError("billing lookup failed")
        return response.json()

    return lookup


def _azure_tokens(credential: Callable[[], Any]) -> Callable[[bool], str]:
    held: list[Any] = []

    def provider(force_refresh: bool) -> str:
        if force_refresh or not held:
            held[:] = [credential()]  # a new credential holds no cached token
        return held[0].get_token("https://management.azure.com/.default").token

    return provider
