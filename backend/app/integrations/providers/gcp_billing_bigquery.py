"""GCP BigQuery billing integration for automatic cost ingestion."""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from google.cloud import bigquery
from google.oauth2 import service_account
from google.api_core.exceptions import GoogleAPIError, BadRequest, Forbidden
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
from app.models.team import Team

logger = logging.getLogger(__name__)


class GCPBillingBigQueryIntegration(IntegrationBase):
    """
    GCP BigQuery billing integration.

    Pulls daily costs from GCP BigQuery billing export and imports them
    into Heliox cost_snapshots table. Supports:
    - Multiple GCP projects
    - Label-based team mapping (e.g., "team" label)
    - Incremental syncs (only fetch since last_sync_at)
    - Idempotent upserts (no duplicates)

    Required configuration:
    - gcp_project_id: GCP project ID where BigQuery dataset exists
    - bigquery_dataset: BigQuery dataset name (e.g., billing_export)
    - service_account_json: Service account JSON key (full JSON string)

    Optional configuration:
    - billing_export_table: Table name (default: gcp_billing_export_v1)
    - label_key_for_team: Label key for team mapping (e.g., "team")
    """

    provider = IntegrationProvider.GCP_BILLING_BIGQUERY
    display_name = "GCP BigQuery Billing"
    description = "Import GPU and infrastructure costs from GCP BigQuery billing export"

    required_config_fields = [
        "gcp_project_id",
        "bigquery_dataset",
        "service_account_json",
    ]
    optional_config_fields = ["billing_export_table", "label_key_for_team"]

    config_schema_fields = {
        "gcp_project_id": {
            "type": "string",
            "description": "GCP project ID where your BigQuery billing export dataset lives",
            "placeholder": "my-gcp-project-123",
            "required": True,
            "secret": False,
        },
        "bigquery_dataset": {
            "type": "string",
            "description": "BigQuery dataset name containing the billing export table",
            "placeholder": "billing_export",
            "required": True,
            "secret": False,
        },
        "service_account_json": {
            "type": "string",
            "description": (
                "Full service account JSON key. The service account requires BigQuery Data Viewer "
                "on the billing dataset. Paste the entire JSON object."
            ),
            "placeholder": '{"type":"service_account","project_id":"..."}',
            "required": True,
            "secret": True,
        },
        "billing_export_table": {
            "type": "string",
            "description": "Table name for the billing export (default: gcp_billing_export_v1)",
            "placeholder": "gcp_billing_export_v1",
            "required": False,
            "secret": False,
        },
        "label_key_for_team": {
            "type": "string",
            "description": (
                "GCP resource label key used to map costs to Heliox teams. "
                "Leave empty to assign all costs to the integration owner team."
            ),
            "placeholder": "team",
            "required": False,
            "secret": False,
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.gcp_project_id = config["gcp_project_id"]
        self.bigquery_dataset = config["bigquery_dataset"]
        self.billing_export_table = config.get("billing_export_table", "gcp_billing_export_v1")
        self.label_key_for_team = config.get("label_key_for_team", "")
        if isinstance(config["service_account_json"], str):
            self.service_account_info = json.loads(config["service_account_json"])
        else:
            self.service_account_info = config["service_account_json"]

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate GCP configuration.

        Raises:
            IntegrationConfigError: If required fields are missing or malformed.
        """
        _provider = "gcp_billing_bigquery"
        for field in self.required_config_fields:
            if field not in config or not config[field]:
                raise IntegrationConfigError(
                    f"Missing required field: {field}",
                    provider=_provider,
                    field=field,
                )

        project_id = config["gcp_project_id"]
        if not isinstance(project_id, str) or len(project_id) < 6:
            raise IntegrationConfigError(
                "gcp_project_id must be a valid GCP project ID (6-30 characters)",
                provider=_provider,
                field="gcp_project_id",
            )

        dataset = config["bigquery_dataset"]
        if not isinstance(dataset, str) or len(dataset) < 1:
            raise IntegrationConfigError(
                "bigquery_dataset must be a valid BigQuery dataset name",
                provider=_provider,
                field="bigquery_dataset",
            )

        # Validate service account JSON structure
        try:
            if isinstance(config["service_account_json"], str):
                sa_info = json.loads(config["service_account_json"])
            else:
                sa_info = config["service_account_json"]
        except json.JSONDecodeError as e:
            raise IntegrationConfigError(
                f"service_account_json is not valid JSON: {e}",
                provider=_provider,
                field="service_account_json",
            )

        required_sa_fields = [
            "type",
            "project_id",
            "private_key_id",
            "private_key",
            "client_email",
        ]
        for field in required_sa_fields:
            if field not in sa_info:
                raise IntegrationConfigError(
                    f"service_account_json missing required field: {field}",
                    provider=_provider,
                    field="service_account_json",
                )

        if sa_info.get("type") != "service_account":
            raise IntegrationConfigError(
                "service_account_json must have type: service_account",
                provider=_provider,
                field="service_account_json",
            )

        logger.debug("GCP BigQuery billing configuration validated successfully")

    def _get_bigquery_client(self) -> bigquery.Client:
        """Create BigQuery client using service account credentials."""
        credentials = service_account.Credentials.from_service_account_info(
            self.service_account_info,
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
        return bigquery.Client(credentials=credentials, project=self.gcp_project_id)

    async def health(self) -> Dict[str, Any]:
        """
        Check GCP BigQuery integration health.

        Tests: credentials → dataset exists → table exists → can query.
        Never raises — all exceptions are caught.
        """
        logger.debug("Checking GCP BigQuery billing integration health")
        try:
            client = self._get_bigquery_client()
            dataset_ref = f"{self.gcp_project_id}.{self.bigquery_dataset}"

            try:
                client.get_dataset(dataset_ref)
                dataset_exists = True
            except Exception as e:
                logger.warning("Dataset %s not accessible: %s", dataset_ref, e)
                dataset_exists = False

            table_ref = f"{dataset_ref}.{self.billing_export_table}"
            table_rows = 0
            try:
                table = client.get_table(table_ref)
                table_exists = True
                table_rows = table.num_rows
            except Exception as e:
                logger.warning("Table %s not accessible: %s", table_ref, e)
                table_exists = False

            can_query = False
            if table_exists:
                try:
                    query = f"SELECT COUNT(*) as count FROM `{table_ref}` LIMIT 1"
                    list(client.query(query).result())
                    can_query = True
                except Exception as e:
                    logger.error("GCP query test failed: %s", e)

            if dataset_exists and table_exists and can_query:
                return {
                    "status": IntegrationHealthStatus.HEALTHY.value,
                    "message": "GCP BigQuery billing connection successful",
                    "details": {
                        "credentials_valid": True,
                        "dataset_exists": True,
                        "table_exists": True,
                        "can_query": True,
                        "project_id": self.gcp_project_id,
                        "dataset": self.bigquery_dataset,
                        "table": self.billing_export_table,
                        "table_rows": table_rows,
                        "service_account": self.service_account_info.get("client_email", "unknown"),
                    },
                }

            if not dataset_exists:
                message = f"BigQuery dataset '{self.bigquery_dataset}' not found or not accessible"
            elif not table_exists:
                message = f"Billing export table '{self.billing_export_table}' not found"
            else:
                message = "Cannot query billing export table — check service account permissions"

            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": message,
                "details": {
                    "credentials_valid": True,
                    "dataset_exists": dataset_exists,
                    "table_exists": table_exists,
                    "can_query": can_query,
                    "project_id": self.gcp_project_id,
                    "service_account": self.service_account_info.get("client_email", "unknown"),
                },
            }

        except Forbidden as e:
            logger.error("GCP permission denied: %s", e)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": "Permission denied — check service account IAM roles (requires BigQuery Data Viewer)",
                "details": {
                    "credentials_valid": True,
                    "error": "Forbidden",
                    "error_message": str(e),
                    "service_account": self.service_account_info.get("client_email", "unknown"),
                },
            }

        except BadRequest as e:
            logger.error("GCP bad request: %s", e)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Invalid request: {str(e)}",
                "details": {
                    "credentials_valid": True,
                    "error": "BadRequest",
                    "error_message": str(e),
                },
            }

        except GoogleAPIError as e:
            logger.error("GCP API error: %s", e)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"GCP API error: {str(e)}",
                "details": {
                    "credentials_valid": False,
                    "error": e.__class__.__name__,
                    "error_message": str(e),
                },
            }

        except Exception as e:
            logger.error("Unexpected error in GCP health check: %s", e, exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Health check failed: {str(e)}",
                "details": {"error": e.__class__.__name__, "error_message": str(e)},
            }

    def _map_team_by_label(self, db: Session, team_id: UUID, label_value: str) -> Optional[Team]:
        team = db.query(Team).filter(Team.name.ilike(f"%{label_value}%")).first()
        if team:
            logger.debug("Mapped label '%s' to team %s", label_value, team.id)
            return team
        logger.debug("No team for label '%s', using owner team %s", label_value, team_id)
        return db.query(Team).filter(Team.id == team_id).first()

    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync cost data from GCP BigQuery billing export.

        Raises:
            IntegrationSyncError: On unrecoverable API or BigQuery failure.
        """
        logger.info("Starting GCP BigQuery billing sync for team %s", team_id)
        db = next(get_db())
        try:
            end_date = datetime.utcnow().date()
            if last_sync_at:
                start_date = last_sync_at.date()
                logger.info("Incremental sync from %s to %s", start_date, end_date)
            else:
                start_date = end_date - timedelta(days=30)
                logger.info("Initial sync: last 30 days (%s to %s)", start_date, end_date)

            table_ref = f"{self.gcp_project_id}.{self.bigquery_dataset}.{self.billing_export_table}"

            if self.label_key_for_team:
                query = f"""
                    SELECT
                        DATE(usage_start_time) as usage_date,
                        service.description as service_name,
                        project.id as project_id,
                        (SELECT value FROM UNNEST(labels) WHERE key = @label_key) as team_label,
                        SUM(cost) as total_cost
                    FROM `{table_ref}`
                    WHERE DATE(usage_start_time) >= @start_date
                      AND DATE(usage_start_time) < @end_date
                      AND cost > 0
                    GROUP BY usage_date, service_name, project_id, team_label
                    ORDER BY usage_date DESC
                """
            else:
                query = f"""
                    SELECT
                        DATE(usage_start_time) as usage_date,
                        service.description as service_name,
                        project.id as project_id,
                        SUM(cost) as total_cost
                    FROM `{table_ref}`
                    WHERE DATE(usage_start_time) >= @start_date
                      AND DATE(usage_start_time) < @end_date
                      AND cost > 0
                    GROUP BY usage_date, service_name, project_id
                    ORDER BY usage_date DESC
                """

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                    bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
                ]
            )
            if self.label_key_for_team:
                job_config.query_parameters.append(
                    bigquery.ScalarQueryParameter("label_key", "STRING", self.label_key_for_team)
                )

            client = self._get_bigquery_client()
            logger.debug("Executing BigQuery billing query")
            results = client.query(query, job_config=job_config).result()

            records_fetched = 0
            records_saved = 0
            records_skipped = 0
            errors: List[str] = []

            for row in results:
                records_fetched += 1
                usage_date = row.usage_date
                service_name = row.service_name or "Unknown"
                total_cost = Decimal(str(row.total_cost))
                team_label = getattr(row, "team_label", None) if self.label_key_for_team else None

                if total_cost <= 0:
                    records_skipped += 1
                    continue

                if team_label and self.label_key_for_team:
                    mapped_team = self._map_team_by_label(db, UUID(team_id), team_label)
                    target_team_id = mapped_team.id if mapped_team else UUID(team_id)
                else:
                    target_team_id = UUID(team_id)

                provider = "gcp"
                service_lower = service_name.lower()
                if "compute engine" in service_lower:
                    gpu_type = "compute-engine"
                elif "vertex ai" in service_lower or "ai platform" in service_lower:
                    gpu_type = "vertex-ai"
                elif "gke" in service_lower or "kubernetes" in service_lower:
                    gpu_type = "gke"
                else:
                    gpu_type = "unknown"

                existing = (
                    db.query(CostSnapshot)
                    .filter(
                        CostSnapshot.team_id == target_team_id,
                        CostSnapshot.date == usage_date,
                        CostSnapshot.provider == provider,
                        CostSnapshot.gpu_type == gpu_type,
                    )
                    .first()
                )

                if existing:
                    existing.cost_usd = existing.cost_usd + total_cost
                    existing.updated_at = datetime.utcnow()
                else:
                    db.add(
                        CostSnapshot(
                            team_id=target_team_id,
                            date=usage_date,
                            provider=provider,
                            gpu_type=gpu_type,
                            cost_usd=total_cost,
                        )
                    )
                records_saved += 1

            db.commit()
            logger.info(
                "GCP sync completed: %d fetched, %d saved, %d skipped",
                records_fetched,
                records_saved,
                records_skipped,
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
                "project_id": self.gcp_project_id,
                "label_key": self.label_key_for_team or None,
            }

        except GoogleAPIError as e:
            logger.error("GCP BigQuery sync failed: %s", e, exc_info=True)
            raise IntegrationSyncError(
                f"GCP API error: {e}",
                provider="gcp_billing_bigquery",
                operation="sync",
                original_error=e,
            )

        except IntegrationSyncError:
            raise

        except Exception as e:
            logger.error("GCP sync failed: %s", e, exc_info=True)
            raise IntegrationSyncError(
                f"GCP sync failed: {e}",
                provider="gcp_billing_bigquery",
                operation="sync",
                original_error=e,
            )

        finally:
            db.close()


# Register the integration
integration_registry.register(IntegrationProvider.GCP_BILLING_BIGQUERY, GCPBillingBigQueryIntegration)
