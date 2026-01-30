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
from app.integrations.base import IntegrationBase, IntegrationProvider, IntegrationHealthStatus
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
    - Label-based team mapping (e.g., team label)
    - Incremental syncs (only fetch since last_sync_at)
    - Idempotent upserts (no duplicates)
    
    Required configuration:
    - gcp_project_id: GCP project ID where BigQuery dataset exists
    - bigquery_dataset: BigQuery dataset name (e.g., billing_export)
    - service_account_json: Service account JSON key (encrypted)
    
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
        "service_account_json"
    ]
    
    optional_config_fields = [
        "billing_export_table",
        "label_key_for_team"
    ]
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with config and create BigQuery client."""
        super().__init__(config)
        
        # Set defaults
        self.gcp_project_id = config["gcp_project_id"]
        self.bigquery_dataset = config["bigquery_dataset"]
        self.billing_export_table = config.get("billing_export_table", "gcp_billing_export_v1")
        self.label_key_for_team = config.get("label_key_for_team", "")
        
        # Parse service account JSON
        if isinstance(config["service_account_json"], str):
            self.service_account_info = json.loads(config["service_account_json"])
        else:
            self.service_account_info = config["service_account_json"]
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate GCP configuration.
        
        Checks that required fields are present. Actual credential validation
        happens in health() check.
        """
        # Check required fields
        for field in self.required_config_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate GCP project ID format
        project_id = config["gcp_project_id"]
        if not isinstance(project_id, str) or len(project_id) < 6:
            raise ValueError("gcp_project_id must be a valid GCP project ID (6-30 characters)")
        
        # Validate BigQuery dataset format
        dataset = config["bigquery_dataset"]
        if not isinstance(dataset, str) or len(dataset) < 1:
            raise ValueError("bigquery_dataset must be a valid BigQuery dataset name")
        
        # Validate service account JSON
        try:
            if isinstance(config["service_account_json"], str):
                sa_info = json.loads(config["service_account_json"])
            else:
                sa_info = config["service_account_json"]
            
            # Check required fields in service account JSON
            required_sa_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
            for field in required_sa_fields:
                if field not in sa_info:
                    raise ValueError(f"Service account JSON missing required field: {field}")
            
            if sa_info["type"] != "service_account":
                raise ValueError("Service account JSON must have type: service_account")
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid service account JSON: {e}")
        except Exception as e:
            raise ValueError(f"Invalid service account configuration: {e}")
        
        logger.debug("GCP BigQuery billing configuration validated successfully")
    
    def _get_bigquery_client(self) -> bigquery.Client:
        """Create BigQuery client with service account credentials."""
        credentials = service_account.Credentials.from_service_account_info(
            self.service_account_info,
            scopes=["https://www.googleapis.com/auth/bigquery"]
        )
        return bigquery.Client(
            credentials=credentials,
            project=self.gcp_project_id
        )
    
    async def health(self) -> Dict[str, Any]:
        """
        Check GCP BigQuery integration health.
        
        Tests:
        1. Service account credentials are valid
        2. BigQuery dataset exists and is accessible
        3. Billing export table exists
        4. Can query the table (LIMIT 1)
        """
        logger.debug("Checking GCP BigQuery billing integration health")
        
        try:
            # Test 1: Create BigQuery client (validates credentials)
            client = self._get_bigquery_client()
            
            # Test 2: Check if dataset exists
            dataset_ref = f"{self.gcp_project_id}.{self.bigquery_dataset}"
            try:
                dataset = client.get_dataset(dataset_ref)
                dataset_exists = True
            except Exception as e:
                logger.warning(f"Dataset {dataset_ref} not accessible: {e}")
                dataset_exists = False
            
            # Test 3: Check if billing export table exists
            table_ref = f"{dataset_ref}.{self.billing_export_table}"
            try:
                table = client.get_table(table_ref)
                table_exists = True
                table_rows = table.num_rows
            except Exception as e:
                logger.warning(f"Table {table_ref} not accessible: {e}")
                table_exists = False
                table_rows = 0
            
            # Test 4: Run a minimal query to verify read access
            if table_exists:
                query = f"""
                    SELECT COUNT(*) as count
                    FROM `{table_ref}`
                    LIMIT 1
                """
                try:
                    query_job = client.query(query)
                    result = list(query_job.result())
                    can_query = True
                except Exception as e:
                    logger.error(f"Query test failed: {e}")
                    can_query = False
            else:
                can_query = False
            
            # If all checks pass, we're healthy
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
                        "service_account": self.service_account_info.get("client_email", "unknown")
                    }
                }
            else:
                # Determine what's wrong
                if not dataset_exists:
                    message = f"BigQuery dataset '{self.bigquery_dataset}' not found or not accessible"
                elif not table_exists:
                    message = f"Billing export table '{self.billing_export_table}' not found"
                elif not can_query:
                    message = "Cannot query billing export table - check permissions"
                else:
                    message = "Unknown health check failure"
                
                return {
                    "status": IntegrationHealthStatus.UNHEALTHY.value,
                    "message": message,
                    "details": {
                        "credentials_valid": True,
                        "dataset_exists": dataset_exists,
                        "table_exists": table_exists,
                        "can_query": can_query,
                        "project_id": self.gcp_project_id,
                        "service_account": self.service_account_info.get("client_email", "unknown")
                    }
                }
        
        except Forbidden as e:
            logger.error(f"GCP permission denied: {e}")
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": "Permission denied - check service account IAM roles",
                "details": {
                    "credentials_valid": True,
                    "error": "Forbidden",
                    "error_message": str(e),
                    "service_account": self.service_account_info.get("client_email", "unknown")
                }
            }
        
        except BadRequest as e:
            logger.error(f"GCP bad request: {e}")
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Invalid request: {str(e)}",
                "details": {
                    "credentials_valid": True,
                    "error": "BadRequest",
                    "error_message": str(e)
                }
            }
        
        except GoogleAPIError as e:
            logger.error(f"GCP API error: {e}")
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"GCP API error: {str(e)}",
                "details": {
                    "credentials_valid": False,
                    "error": e.__class__.__name__,
                    "error_message": str(e)
                }
            }
        
        except Exception as e:
            logger.error(f"Unexpected error in GCP health check: {e}", exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Health check failed: {str(e)}",
                "details": {
                    "error": e.__class__.__name__,
                    "error_message": str(e)
                }
            }
    
    def _map_team_by_label(self, db: Session, team_id: UUID, label_value: str) -> Optional[Team]:
        """
        Map GCP label value to Heliox team.
        
        Args:
            db: Database session
            team_id: Integration owner team ID (fallback)
            label_value: Label value (e.g., "ml-research")
            
        Returns:
            Team object or None
        """
        # Try to find team by name matching label value
        team = db.query(Team).filter(
            Team.name.ilike(f"%{label_value}%")
        ).first()
        
        if team:
            logger.debug(f"Mapped label value '{label_value}' to team {team.id}")
            return team
        
        # Fallback to integration owner team
        logger.debug(f"No team found for label value '{label_value}', using owner team {team_id}")
        return db.query(Team).filter(Team.id == team_id).first()
    
    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync cost data from GCP BigQuery billing export.
        
        Steps:
        1. Determine date range (last 30 days or since last_sync_at)
        2. Query BigQuery billing export
        3. Transform results to cost_snapshots format
        4. Upsert to database (idempotent)
        5. Map teams using labels if configured
        
        Args:
            team_id: Heliox team ID (owner of this integration)
            last_sync_at: Last successful sync timestamp
            
        Returns:
            Sync metrics dictionary
        """
        logger.info(f"Starting GCP BigQuery billing sync for team {team_id}")
        
        db = next(get_db())
        
        try:
            # Determine date range
            end_date = datetime.utcnow().date()
            
            if last_sync_at:
                # Incremental: sync from last successful sync
                start_date = last_sync_at.date()
                logger.info(f"Incremental sync from {start_date} to {end_date}")
            else:
                # Initial sync: last 30 days
                start_date = end_date - timedelta(days=30)
                logger.info(f"Initial sync: last 30 days ({start_date} to {end_date})")
            
            # Build BigQuery query
            table_ref = f"{self.gcp_project_id}.{self.bigquery_dataset}.{self.billing_export_table}"
            
            # Base query: aggregate daily costs by service and project
            if self.label_key_for_team:
                # Include label in grouping
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
                # No label grouping
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
            
            # Query parameters
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
            
            # Execute query
            client = self._get_bigquery_client()
            logger.debug(f"Executing BigQuery query: {query}")
            query_job = client.query(query, job_config=job_config)
            results = query_job.result()
            
            # Process results
            records_fetched = 0
            records_saved = 0
            records_skipped = 0
            errors = []
            
            for row in results:
                records_fetched += 1
                
                # Parse row
                usage_date = row.usage_date
                service_name = row.service_name or "Unknown"
                project_id = row.project_id or "unknown"
                total_cost = Decimal(str(row.total_cost))
                team_label = getattr(row, 'team_label', None) if self.label_key_for_team else None
                
                # Skip zero costs (should be filtered by query, but just in case)
                if total_cost <= 0:
                    records_skipped += 1
                    continue
                
                # Map to team
                if team_label and self.label_key_for_team:
                    mapped_team = self._map_team_by_label(db, UUID(team_id), team_label)
                    target_team_id = mapped_team.id if mapped_team else UUID(team_id)
                else:
                    target_team_id = UUID(team_id)
                
                # Map service to provider/GPU type
                provider = "gcp"
                gpu_type = "unknown"
                
                # Try to extract GPU type from service name
                service_lower = service_name.lower()
                if "compute engine" in service_lower:
                    gpu_type = "compute-engine"
                elif "vertex ai" in service_lower or "ai platform" in service_lower:
                    gpu_type = "vertex-ai"
                elif "gke" in service_lower or "kubernetes" in service_lower:
                    gpu_type = "gke"
                
                # Upsert cost snapshot (idempotent)
                existing = db.query(CostSnapshot).filter(
                    CostSnapshot.team_id == target_team_id,
                    CostSnapshot.date == usage_date,
                    CostSnapshot.provider == provider,
                    CostSnapshot.gpu_type == gpu_type
                ).first()
                
                if existing:
                    # Update existing record (aggregate if multiple services)
                    existing.cost_usd = existing.cost_usd + total_cost
                    existing.updated_at = datetime.utcnow()
                    records_saved += 1
                    logger.debug(f"Updated cost snapshot: {usage_date} {provider} {gpu_type} += ${total_cost}")
                else:
                    # Create new record
                    snapshot = CostSnapshot(
                        team_id=target_team_id,
                        date=usage_date,
                        provider=provider,
                        gpu_type=gpu_type,
                        cost_usd=total_cost
                    )
                    db.add(snapshot)
                    records_saved += 1
                    logger.debug(f"Created cost snapshot: {usage_date} {provider} {gpu_type} = ${total_cost}")
            
            # Commit all changes
            db.commit()
            
            logger.info(f"GCP sync completed: {records_fetched} fetched, {records_saved} saved, {records_skipped} skipped")
            
            return {
                "records_fetched": records_fetched,
                "records_saved": records_saved,
                "records_skipped": records_skipped,
                "errors": errors,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "project_id": self.gcp_project_id,
                "label_key": self.label_key_for_team or None
            }
        
        except GoogleAPIError as e:
            logger.error(f"GCP BigQuery sync failed: {e}", exc_info=True)
            raise Exception(f"GCP API error: {str(e)}")
        
        except Exception as e:
            logger.error(f"GCP sync failed: {e}", exc_info=True)
            raise
        
        finally:
            db.close()


# Register the integration
integration_registry.register(IntegrationProvider.GCP_BILLING_BIGQUERY, GCPBillingBigQueryIntegration)
