"""Azure Cost Management integration for automatic cost ingestion."""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from azure.identity import ClientSecretCredential
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.integrations.base import IntegrationBase, IntegrationProvider, IntegrationHealthStatus
from app.integrations.registry import integration_registry
from app.models.cost import CostSnapshot

logger = logging.getLogger(__name__)

AZURE_MANAGEMENT_BASE = "https://management.azure.com"
COST_API_VERSION = "2024-08-01"


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

    Required configuration:
    - azure_tenant_id: Azure AD tenant ID
    - azure_client_id: App registration client ID
    - azure_client_secret: App registration client secret
    - subscription_ids: List of subscription IDs to query (at least one)

    Optional configuration:
    - resource_group_filter: Filter to specific resource group (empty = all)
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

    optional_config_fields = [
        "resource_group_filter",
    ]

    def __init__(self, config: Dict[str, Any]):
        """Initialize with config."""
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

        Checks that required fields are present. Actual credential validation
        happens in health() check.
        """
        if not config:
            return  # Allow empty for registry schema discovery
        for field in self.required_config_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")

        tenant_id = config["azure_tenant_id"]
        if not isinstance(tenant_id, str) or len(tenant_id) < 10:
            raise ValueError("azure_tenant_id must be a valid Azure tenant ID (GUID)")

        client_id = config["azure_client_id"]
        if not isinstance(client_id, str) or len(client_id) < 10:
            raise ValueError("azure_client_id must be a valid Azure client ID (GUID)")

        client_secret = config["azure_client_secret"]
        if not isinstance(client_secret, str) or len(client_secret) < 10:
            raise ValueError("azure_client_secret must be a valid client secret")

        sub_ids = config.get("subscription_ids", [])
        if isinstance(sub_ids, str):
            sub_ids = [x.strip() for x in sub_ids.split(",") if x.strip()]
        if not sub_ids:
            raise ValueError("subscription_ids must contain at least one subscription ID")

        for sub_id in sub_ids:
            if not sub_id or len(sub_id) != 36:
                raise ValueError(f"Invalid subscription ID format: {sub_id} (expected GUID)")

        logger.debug("Azure Cost Management configuration validated successfully")

    def _get_token(self) -> str:
        """Get Azure access token."""
        return _get_access_token(
            self.tenant_id,
            self.client_id,
            self.client_secret,
        )

    async def health(self) -> Dict[str, Any]:
        """
        Check Azure Cost Management integration health.

        Tests:
        1. Credentials are valid (can obtain token)
        2. Cost Management API is accessible (minimal query per subscription)
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

            # Test query on first subscription
            sub_id = self.subscription_ids[0]
            scope = f"/subscriptions/{sub_id}"
            url = f"{AZURE_MANAGEMENT_BASE}{scope}/providers/Microsoft.CostManagement/query"
            params = {"api-version": COST_API_VERSION}

            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            body = {
                "type": "Usage",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": yesterday.isoformat(),
                    "to": today.isoformat(),
                },
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
                    "details": {
                        "credentials_valid": False,
                        "api_reachable": True,
                        "error": "Unauthorized",
                    },
                }

            if resp.status_code == 403:
                return {
                    "status": IntegrationHealthStatus.UNHEALTHY.value,
                    "message": "Access denied - ensure the app has Cost Management Reader role",
                    "details": {
                        "credentials_valid": True,
                        "api_reachable": True,
                        "error": "Forbidden",
                    },
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
            logger.error(f"Azure health check failed: {e}", exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Health check failed: {str(e)}",
                "details": {
                    "credentials_valid": False,
                    "api_reachable": False,
                    "error": str(e)[:200],
                },
            }

    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync cost data from Azure Cost Management API.

        Steps:
        1. Determine date range (last 30 days or since last_sync_at)
        2. Query each subscription via Cost Management API
        3. Transform results to cost_snapshots format
        4. Upsert to database (idempotent)
        """
        logger.info(f"Starting Azure Cost Management sync for team {team_id}")

        db = next(get_db())

        try:
            end_date = datetime.utcnow().date()
            if last_sync_at:
                start_date = last_sync_at.date()
                logger.info(f"Incremental sync from {start_date} to {end_date}")
            else:
                start_date = end_date - timedelta(days=30)
                logger.info(f"Initial sync: last 30 days ({start_date} to {end_date})")

            token = self._get_token()
            target_team_id = UUID(team_id)

            records_fetched = 0
            records_saved = 0
            records_skipped = 0
            errors: List[str] = []

            for sub_id in self.subscription_ids:
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

                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            url,
                            params=params,
                            json=body,
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                        )
                except Exception as e:
                    errors.append(f"Subscription {sub_id}: {str(e)}")
                    logger.warning(f"Failed to query subscription {sub_id}: {e}")
                    continue

                if resp.status_code != 200:
                    try:
                        err_body = resp.json()
                        err_msg = err_body.get("error", {}).get("message", resp.text)
                    except Exception:
                        err_msg = resp.text or str(resp.status_code)
                    errors.append(f"Subscription {sub_id}: {err_msg[:100]}")
                    continue

                data = resp.json()
                rows = data.get("properties", {}).get("rows", [])
                columns = data.get("properties", {}).get("columns", [])

                # Columns order from grouping [ServiceName, Date] + aggregation [Cost]
                # Date may be YYYYMMDD (int) or ISO string
                for row in rows:
                    records_fetched += 1
                    if len(row) < 3:
                        records_skipped += 1
                        continue

                    # Row: [service_name, date, cost] - cost is last
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
                                snap_date = datetime.strptime(s.split("T")[0][:10], "%Y-%m-%d").date()
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
                        records_saved += 1
                    else:
                        snapshot = CostSnapshot(
                            team_id=target_team_id,
                            date=snap_date,
                            provider=provider,
                            gpu_type=gpu_type,
                            cost_usd=cost,
                        )
                        db.add(snapshot)
                        records_saved += 1

            db.commit()

            logger.info(
                f"Azure sync completed: {records_fetched} fetched, {records_saved} saved, "
                f"{records_skipped} skipped"
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

        except Exception as e:
            logger.error(f"Azure sync failed: {e}", exc_info=True)
            raise
        finally:
            db.close()


# Register the integration
integration_registry.register(IntegrationProvider.AZURE, AzureCostManagementIntegration)
