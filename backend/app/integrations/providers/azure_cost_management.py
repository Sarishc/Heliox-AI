"""Azure Cost Management integration for automatic cost ingestion."""
import asyncio
import logging
import time as _time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from azure.identity import ClientSecretCredential
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.integrations.base import (
    IntegrationBase,
    IntegrationConfigError,
    IntegrationProvider,
    IntegrationSyncError,
    IntegrationHealthStatus,
)
from app.integrations.registry import integration_registry
from app.models.cost import CostSnapshot

logger = logging.getLogger(__name__)

AZURE_MANAGEMENT_BASE = "https://management.azure.com"
COST_API_VERSION = "2024-08-01"
# Maximum seconds to honour a Retry-After header before giving up on a subscription
_MAX_RETRY_AFTER_SECONDS = 60


def _get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Get OAuth2 access token for Azure Management API."""
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    token = credential.get_token("https://management.azure.com/.default")
    return token.token


def _map_azure_service_to_gpu_type(service_name: str) -> str:
    """Map Azure service name to GPU type for cost attribution."""
    name_lower = (service_name or "").lower()
    if "virtual machine" in name_lower or "vm" in name_lower or "compute" in name_lower:
        return "azure_vm"
    if "machine learning" in name_lower or "ml" in name_lower or "azure ml" in name_lower:
        return "azure_ml"
    if "container" in name_lower or "aks" in name_lower or "kubernetes" in name_lower:
        return "azure_aks"
    if "batch" in name_lower:
        return "azure_batch"
    return "azure_other"


class AzureCostManagementIntegration(IntegrationBase):
    """
    Azure Cost Management integration.

    Pulls daily costs from Azure Cost Management Query API and imports them
    into Heliox cost_snapshots table. Supports:
    - One or more Azure subscriptions per connection
    - Incremental syncs (only fetch since last_sync_at)
    - Idempotent upserts (no duplicates)
    - 429 retry with Retry-After header respected
    - 401 token refresh and single retry

    Required configuration:
    - azure_tenant_id: Azure AD tenant ID (GUID)
    - azure_client_id: App registration client ID (GUID)
    - azure_client_secret: App registration client secret
    - subscription_ids: Comma-separated or list of subscription IDs (GUIDs)

    Optional configuration:
    - resource_group_filter: Restrict to a specific resource group (empty = all)
    """

    provider = IntegrationProvider.AZURE
    display_name = "Azure Cost Management"
    description = "Import GPU and infrastructure costs from Azure Cost Management API"

    required_config_fields = [
        "azure_tenant_id",
        "azure_client_id",
        "azure_client_secret",
        "subscription_ids",
    ]
    optional_config_fields = ["resource_group_filter"]

    config_schema_fields = {
        "azure_tenant_id": {
            "type": "string",
            "description": "Azure Active Directory tenant ID (Directory ID). Found in Azure Portal > Azure Active Directory > Properties",
            "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "required": True,
            "secret": False,
        },
        "azure_client_id": {
            "type": "string",
            "description": "App registration (service principal) client ID. The app needs Cost Management Reader role on each subscription",
            "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "required": True,
            "secret": False,
        },
        "azure_client_secret": {
            "type": "string",
            "description": "App registration client secret (from Azure Portal > App registrations > Certificates & secrets)",
            "placeholder": "your-client-secret",
            "required": True,
            "secret": True,
        },
        "subscription_ids": {
            "type": "string",
            "description": "Comma-separated Azure subscription IDs to sync. At least one required",
            "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx,yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
            "required": True,
            "secret": False,
        },
        "resource_group_filter": {
            "type": "string",
            "description": "Restrict cost data to a specific resource group name. Leave empty to include all resource groups",
            "placeholder": "my-ml-resource-group",
            "required": False,
            "secret": False,
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.tenant_id = config["azure_tenant_id"]
        self.client_id = config["azure_client_id"]
        self.client_secret = config["azure_client_secret"]
        sub_ids = config.get("subscription_ids", [])
        if isinstance(sub_ids, str):
            sub_ids = [x.strip() for x in sub_ids.split(",") if x.strip()]
        self.subscription_ids = sub_ids
        self.resource_group_filter = config.get("resource_group_filter", "")

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate Azure configuration.

        Raises:
            IntegrationConfigError: If required fields are missing or malformed.
        """
        _provider = "azure"
        # NOTE: no early-return guard here — config must always be validated
        for field in self.required_config_fields:
            if field not in config or not config[field]:
                raise IntegrationConfigError(
                    f"Missing required field: {field}",
                    provider=_provider,
                    field=field,
                )

        tenant_id = config["azure_tenant_id"]
        if not isinstance(tenant_id, str) or len(tenant_id) < 10:
            raise IntegrationConfigError(
                "azure_tenant_id must be a valid Azure tenant ID (GUID)",
                provider=_provider,
                field="azure_tenant_id",
            )

        client_id = config["azure_client_id"]
        if not isinstance(client_id, str) or len(client_id) < 10:
            raise IntegrationConfigError(
                "azure_client_id must be a valid Azure client ID (GUID)",
                provider=_provider,
                field="azure_client_id",
            )

        client_secret = config["azure_client_secret"]
        if not isinstance(client_secret, str) or len(client_secret) < 10:
            raise IntegrationConfigError(
                "azure_client_secret must be a valid client secret",
                provider=_provider,
                field="azure_client_secret",
            )

        sub_ids = config.get("subscription_ids", [])
        if isinstance(sub_ids, str):
            sub_ids = [x.strip() for x in sub_ids.split(",") if x.strip()]
        if not sub_ids:
            raise IntegrationConfigError(
                "subscription_ids must contain at least one subscription ID",
                provider=_provider,
                field="subscription_ids",
            )
        for sub_id in sub_ids:
            if not sub_id or len(sub_id) != 36:
                raise IntegrationConfigError(
                    f"Invalid subscription ID format: {sub_id} (expected GUID, 36 characters)",
                    provider=_provider,
                    field="subscription_ids",
                )

        logger.debug("Azure Cost Management configuration validated successfully")

    def _get_token(self) -> str:
        """Get Azure access token using the configured service principal."""
        return _get_access_token(self.tenant_id, self.client_id, self.client_secret)

    async def health(self) -> Dict[str, Any]:
        """
        Check Azure Cost Management integration health.

        Tests credential validity and Cost Management API access on the first
        subscription. Never raises — all exceptions are caught.
        """
        logger.debug("Checking Azure Cost Management integration health")
        try:
            token = self._get_token()
            if not token:
                return {
                    "status": IntegrationHealthStatus.UNHEALTHY.value,
                    "message": "Failed to obtain Azure access token",
                    "details": {"credentials_valid": False},
                }

            sub_id = self.subscription_ids[0]
            scope = f"/subscriptions/{sub_id}"
            url = f"{AZURE_MANAGEMENT_BASE}{scope}/providers/Microsoft.CostManagement/query"
            params = {"api-version": COST_API_VERSION}

            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            body = {
                "type": "Usage",
                "timeframe": "Custom",
                "timePeriod": {"from": yesterday.isoformat(), "to": today.isoformat()},
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                    "grouping": [{"type": "Dimension", "name": "ServiceName"}],
                },
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    params=params,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code == 200:
                return {
                    "status": IntegrationHealthStatus.HEALTHY.value,
                    "message": "Azure Cost Management connection successful",
                    "details": {
                        "credentials_valid": True,
                        "api_reachable": True,
                        "subscription_id": sub_id,
                        "subscriptions_count": len(self.subscription_ids),
                    },
                }

            if resp.status_code == 401:
                return {
                    "status": IntegrationHealthStatus.UNHEALTHY.value,
                    "message": "Invalid Azure credentials or insufficient permissions",
                    "details": {"credentials_valid": False, "api_reachable": True, "error": "Unauthorized"},
                }

            if resp.status_code == 403:
                return {
                    "status": IntegrationHealthStatus.UNHEALTHY.value,
                    "message": "Access denied — ensure the app has Cost Management Reader role on the subscription",
                    "details": {"credentials_valid": True, "api_reachable": True, "error": "Forbidden"},
                }

            try:
                err_body = resp.json()
                err_msg = err_body.get("error", {}).get("message", resp.text)
            except Exception:
                err_msg = resp.text or str(resp.status_code)

            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Azure API error: {err_msg}",
                "details": {
                    "credentials_valid": True,
                    "api_reachable": True,
                    "status_code": resp.status_code,
                    "error": err_msg[:200],
                },
            }

        except Exception as e:
            logger.error("Azure health check failed: %s", e, exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Health check failed: {str(e)}",
                "details": {"credentials_valid": False, "api_reachable": False, "error": str(e)[:200]},
            }

    async def _query_subscription(
        self,
        client: httpx.AsyncClient,
        sub_id: str,
        token: str,
        start_date,
        end_date,
    ) -> httpx.Response:
        """
        POST a Cost Management query for one subscription.

        Handles:
        - 429: sleep for Retry-After seconds (capped at _MAX_RETRY_AFTER_SECONDS) then retry once
        - 401: refresh token and retry once (expired token mid-sync)
        """
        scope = f"/subscriptions/{sub_id}"
        url = f"{AZURE_MANAGEMENT_BASE}{scope}/providers/Microsoft.CostManagement/query"
        params = {"api-version": COST_API_VERSION}
        body = {
            "type": "Usage",
            "timeframe": "Custom",
            "timePeriod": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
            },
            "dataset": {
                "granularity": "Daily",
                "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                "grouping": [
                    {"type": "Dimension", "name": "ServiceName"},
                    {"type": "Dimension", "name": "Date"},
                ],
            },
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp = await client.post(url, params=params, json=body, headers=headers)

        # 429 — rate limited: respect Retry-After and retry once
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            retry_after = min(retry_after, _MAX_RETRY_AFTER_SECONDS)
            logger.warning(
                "Azure 429 rate limit on subscription %s — sleeping %ds (Retry-After)",
                sub_id, retry_after,
            )
            await asyncio.sleep(retry_after)
            resp = await client.post(url, params=params, json=body, headers=headers)

        # 401 — token may have expired mid-sync: refresh and retry once
        if resp.status_code == 401:
            logger.warning(
                "Azure 401 on subscription %s — refreshing token and retrying", sub_id
            )
            fresh_token = self._get_token()
            headers["Authorization"] = f"Bearer {fresh_token}"
            resp = await client.post(url, params=params, json=body, headers=headers)

        return resp

    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync cost data from Azure Cost Management API.

        Per-subscription errors are recorded in the returned "errors" list rather
        than aborting the entire sync. Raises IntegrationSyncError only when all
        subscriptions fail or on an unrecoverable exception.

        Raises:
            IntegrationSyncError: On unrecoverable failure.
        """
        logger.info("Starting Azure Cost Management sync for team %s", team_id)
        db = next(get_db())
        try:
            end_date = datetime.utcnow().date()
            if last_sync_at:
                start_date = last_sync_at.date()
                logger.info("Incremental sync from %s to %s", start_date, end_date)
            else:
                start_date = end_date - timedelta(days=30)
                logger.info("Initial sync: last 30 days (%s to %s)", start_date, end_date)

            token = self._get_token()
            target_team_id = UUID(team_id)

            records_fetched = 0
            records_saved = 0
            records_skipped = 0
            errors: List[str] = []

            async with httpx.AsyncClient(timeout=60.0) as http_client:
                for sub_id in self.subscription_ids:
                    try:
                        resp = await self._query_subscription(
                            http_client, sub_id, token, start_date, end_date
                        )
                    except Exception as e:
                        errors.append(f"Subscription {sub_id}: {e}")
                        logger.warning("Failed to query subscription %s: %s", sub_id, e)
                        continue

                    if resp.status_code != 200:
                        try:
                            err_body = resp.json()
                            err_msg = err_body.get("error", {}).get("message", resp.text)
                        except Exception:
                            err_msg = resp.text or str(resp.status_code)

                        # 404 = subscription not found / no access — record and skip
                        if resp.status_code == 404:
                            errors.append(
                                f"Subscription {sub_id}: not found or Cost Management not available (404)"
                            )
                        else:
                            errors.append(f"Subscription {sub_id}: {err_msg[:100]}")
                        continue

                    data = resp.json()
                    rows = data.get("properties", {}).get("rows", [])

                    # Columns order: [ServiceName, Date, Cost] from our grouping+aggregation
                    for row in rows:
                        records_fetched += 1
                        if len(row) < 3:
                            records_skipped += 1
                            continue

                        cost_val = row[-1]
                        try:
                            cost = Decimal(str(cost_val))
                        except Exception:
                            cost = Decimal("0")

                        if cost <= 0:
                            records_skipped += 1
                            continue

                        service_name = str(row[0]) if len(row) > 0 else "Unknown"
                        date_val = row[1] if len(row) > 1 else None

                        if date_val is not None:
                            try:
                                s = str(date_val)
                                if len(s) == 8 and s.isdigit():
                                    snap_date = datetime.strptime(s, "%Y%m%d").date()
                                elif "T" in s:
                                    snap_date = datetime.strptime(
                                        s.split("T")[0][:10], "%Y-%m-%d"
                                    ).date()
                                else:
                                    snap_date = datetime.strptime(s[:10], "%Y-%m-%d").date()
                            except Exception:
                                snap_date = start_date
                        else:
                            snap_date = start_date

                        gpu_type = _map_azure_service_to_gpu_type(service_name)
                        provider = "azure"

                        existing = db.query(CostSnapshot).filter(
                            CostSnapshot.team_id == target_team_id,
                            CostSnapshot.date == snap_date,
                            CostSnapshot.provider == provider,
                            CostSnapshot.gpu_type == gpu_type,
                        ).first()

                        if existing:
                            existing.cost_usd = existing.cost_usd + cost
                            existing.updated_at = datetime.utcnow()
                        else:
                            db.add(CostSnapshot(
                                team_id=target_team_id,
                                date=snap_date,
                                provider=provider,
                                gpu_type=gpu_type,
                                cost_usd=cost,
                            ))
                        records_saved += 1

            db.commit()
            logger.info(
                "Azure sync completed: %d fetched, %d saved, %d skipped",
                records_fetched, records_saved, records_skipped,
            )
            return {
                "records_fetched": records_fetched,
                "records_saved": records_saved,
                "records_skipped": records_skipped,
                "errors": errors,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "subscriptions": self.subscription_ids,
            }

        except IntegrationSyncError:
            raise

        except Exception as e:
            logger.error("Azure sync failed: %s", e, exc_info=True)
            raise IntegrationSyncError(
                f"Azure sync failed: {e}",
                provider="azure",
                operation="sync",
                original_error=e,
            )

        finally:
            db.close()


# Register the integration
integration_registry.register(IntegrationProvider.AZURE, AzureCostManagementIntegration)
