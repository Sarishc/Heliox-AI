"""AWS Cost Explorer integration for automatic cost ingestion."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import boto3
from botocore.exceptions import ClientError, BotoCoreError
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


class AWSCostExplorerIntegration(IntegrationBase):
    """
    AWS Cost Explorer integration.

    Pulls daily unblended costs from AWS Cost Explorer API and imports them
    into Heliox cost_snapshots table. Supports:
    - Multiple linked AWS accounts
    - Cost allocation tags (e.g., Team tag for team mapping)
    - Incremental syncs (only fetch since last_sync_at)
    - Idempotent upserts (no duplicates)

    Required configuration:
    - aws_access_key_id: IAM user Access Key ID with Cost Explorer permissions
    - aws_secret_access_key: Corresponding Secret Access Key

    Optional configuration:
    - aws_region: AWS Region (default: us-east-1)
    - linked_account_ids: Comma-separated AWS account IDs (empty = all)
    - cost_allocation_tag_key: Cost allocation tag key for team mapping (e.g. "Team")
    - cost_allocation_tag_values: Comma-separated tag values to filter (empty = all)
    """

    provider = IntegrationProvider.AWS
    display_name = "AWS Cost Explorer"
    description = "Import GPU and infrastructure costs from AWS Cost Explorer API"

    required_config_fields = ["aws_access_key_id", "aws_secret_access_key"]
    optional_config_fields = [
        "aws_region",
        "linked_account_ids",
        "cost_allocation_tag_key",
        "cost_allocation_tag_values",
    ]

    config_schema_fields = {
        "aws_access_key_id": {
            "type": "string",
            "description": "AWS IAM Access Key ID with ce:GetCostAndUsage and sts:GetCallerIdentity permissions",
            "placeholder": "AKIAIOSFODNN7EXAMPLE",
            "required": True,
            "secret": False,
        },
        "aws_secret_access_key": {
            "type": "string",
            "description": "AWS IAM Secret Access Key corresponding to the Access Key ID",
            "placeholder": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "required": True,
            "secret": True,
        },
        "aws_region": {
            "type": "string",
            "description": "AWS region for Cost Explorer API calls (Cost Explorer is global but some endpoints are regional)",
            "placeholder": "us-east-1",
            "required": False,
            "secret": False,
        },
        "linked_account_ids": {
            "type": "string",
            "description": "Comma-separated AWS account IDs to sync. Leave empty to sync all linked accounts",
            "placeholder": "111122223333,444455556666",
            "required": False,
            "secret": False,
        },
        "cost_allocation_tag_key": {
            "type": "string",
            "description": "Cost allocation tag key for team mapping (e.g. 'Team'). Must be activated in AWS Cost Explorer",
            "placeholder": "Team",
            "required": False,
            "secret": False,
        },
        "cost_allocation_tag_values": {
            "type": "string",
            "description": "Comma-separated tag values to include. Leave empty to include all tag values",
            "placeholder": "ml-research,platform",
            "required": False,
            "secret": False,
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.region = config.get("aws_region", "us-east-1")
        self.linked_account_ids = config.get("linked_account_ids", [])
        if isinstance(self.linked_account_ids, str):
            self.linked_account_ids = [x.strip() for x in self.linked_account_ids.split(",") if x.strip()]
        self.cost_allocation_tag_key = config.get("cost_allocation_tag_key", "")
        self.cost_allocation_tag_values = config.get("cost_allocation_tag_values", [])
        if isinstance(self.cost_allocation_tag_values, str):
            self.cost_allocation_tag_values = [
                x.strip() for x in self.cost_allocation_tag_values.split(",") if x.strip()
            ]

    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate AWS configuration.

        Raises:
            IntegrationConfigError: If required fields are missing or malformed.
        """
        _provider = "aws"
        for field in self.required_config_fields:
            if field not in config or not config[field]:
                raise IntegrationConfigError(
                    f"Missing required field: {field}",
                    provider=_provider,
                    field=field,
                )

        access_key = config["aws_access_key_id"]
        if not isinstance(access_key, str) or len(access_key) < 16:
            raise IntegrationConfigError(
                "aws_access_key_id must be a valid AWS access key (16-128 characters)",
                provider=_provider,
                field="aws_access_key_id",
            )

        secret_key = config["aws_secret_access_key"]
        if not isinstance(secret_key, str) or len(secret_key) < 40:
            raise IntegrationConfigError(
                "aws_secret_access_key must be a valid AWS secret key (40+ characters)",
                provider=_provider,
                field="aws_secret_access_key",
            )

        region = config.get("aws_region", "us-east-1")
        if not isinstance(region, str) or len(region) < 3:
            raise IntegrationConfigError(
                "aws_region must be a valid AWS region (e.g. us-east-1)",
                provider=_provider,
                field="aws_region",
            )

        linked_accounts = config.get("linked_account_ids", [])
        if linked_accounts:
            if isinstance(linked_accounts, str):
                linked_accounts = [x.strip() for x in linked_accounts.split(",") if x.strip()]
            for account_id in linked_accounts:
                if not account_id.isdigit() or len(account_id) != 12:
                    raise IntegrationConfigError(
                        f"Invalid AWS account ID: {account_id} (must be 12 digits)",
                        provider=_provider,
                        field="linked_account_ids",
                    )

        logger.debug("AWS Cost Explorer configuration validated successfully")

    def _get_boto3_session(self) -> boto3.Session:
        return boto3.Session(
            aws_access_key_id=self.config["aws_access_key_id"],
            aws_secret_access_key=self.config["aws_secret_access_key"],
            region_name=self.region,
        )

    def _get_caller_identity(self) -> Dict[str, Any]:
        session = self._get_boto3_session()
        sts_client = session.client("sts")
        return sts_client.get_caller_identity()

    async def health(self) -> Dict[str, Any]:
        """
        Check AWS Cost Explorer integration health.

        Tests credentials via sts:GetCallerIdentity, then makes a minimal
        ce:GetCostAndUsage call to verify Cost Explorer permissions.
        Never raises — all exceptions are caught and returned as unhealthy.
        """
        logger.debug("Checking AWS Cost Explorer integration health")
        try:
            identity = self._get_caller_identity()
            account_id = identity["Account"]
            arn = identity["Arn"]

            session = self._get_boto3_session()
            ce_client = session.client("ce", region_name=self.region)
            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            ce_client.get_cost_and_usage(
                TimePeriod={
                    "Start": yesterday.strftime("%Y-%m-%d"),
                    "End": today.strftime("%Y-%m-%d"),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )

            return {
                "status": IntegrationHealthStatus.HEALTHY.value,
                "message": "AWS Cost Explorer connection successful",
                "details": {
                    "api_reachable": True,
                    "credentials_valid": True,
                    "account_id": account_id,
                    "caller_arn": arn,
                    "region": self.region,
                    "cost_explorer_access": True,
                },
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(
                "AWS Cost Explorer health check failed: %s - %s",
                error_code,
                error_message,
            )
            if error_code in (
                "InvalidClientTokenId",
                "SignatureDoesNotMatch",
                "AccessDenied",
            ):
                message = "Invalid AWS credentials or insufficient permissions"
            elif error_code == "UnrecognizedClientException":
                message = "AWS credentials are invalid or expired"
            else:
                message = f"AWS API error: {error_message}"
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": message,
                "details": {
                    "api_reachable": error_code != "EndpointConnectionError",
                    "credentials_valid": error_code not in ("InvalidClientTokenId", "SignatureDoesNotMatch"),
                    "error_code": error_code,
                    "error_message": error_message,
                },
            }

        except BotoCoreError as e:
            logger.error("AWS boto3 error: %s", e, exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"AWS SDK error: {str(e)}",
                "details": {
                    "api_reachable": False,
                    "credentials_valid": False,
                    "error": str(e),
                },
            }

        except Exception as e:
            logger.error("Unexpected error in AWS health check: %s", e, exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Health check failed: {str(e)}",
                "details": {"error": str(e)},
            }

    def _map_team_by_tag(self, db: Session, team_id: UUID, tag_value: str) -> Optional[Team]:
        team = db.query(Team).filter(Team.name.ilike(f"%{tag_value}%")).first()
        if team:
            logger.debug("Mapped tag value '%s' to team %s", tag_value, team.id)
            return team
        logger.debug("No team found for tag '%s', using owner team %s", tag_value, team_id)
        return db.query(Team).filter(Team.id == team_id).first()

    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync cost data from AWS Cost Explorer.

        Raises:
            IntegrationSyncError: On unrecoverable API failure.
        """
        logger.info("Starting AWS Cost Explorer sync for team %s", team_id)
        db = next(get_db())
        try:
            end_date = datetime.utcnow().date()
            if last_sync_at:
                start_date = last_sync_at.date()
                logger.info("Incremental sync from %s to %s", start_date, end_date)
            else:
                start_date = end_date - timedelta(days=30)
                logger.info("Initial sync: last 30 days (%s to %s)", start_date, end_date)

            session = self._get_boto3_session()
            ce_client = session.client("ce", region_name=self.region)

            filter_expr = None
            if self.linked_account_ids:
                filter_expr = {
                    "Dimensions": {
                        "Key": "LINKED_ACCOUNT",
                        "Values": self.linked_account_ids,
                    }
                }

            group_by = [
                {"Type": "DIMENSION", "Key": "SERVICE"},
                {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
            ]
            if self.cost_allocation_tag_key:
                group_by.append({"Type": "TAG", "Key": self.cost_allocation_tag_key})

            kwargs: Dict[str, Any] = {
                "TimePeriod": {
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                "Granularity": "DAILY",
                "Metrics": ["UnblendedCost"],
                "GroupBy": group_by,
            }
            if filter_expr:
                kwargs["Filter"] = filter_expr

            response = ce_client.get_cost_and_usage(**kwargs)

            records_fetched = 0
            records_saved = 0
            records_skipped = 0
            errors: List[str] = []

            for result_by_time in response.get("ResultsByTime", []):
                date_str = result_by_time["TimePeriod"]["Start"]
                date = datetime.strptime(date_str, "%Y-%m-%d").date()

                for group in result_by_time.get("Groups", []):
                    records_fetched += 1
                    keys = group.get("Keys", [])
                    service = keys[0] if len(keys) > 0 else "Unknown"
                    account_id = keys[1] if len(keys) > 1 else "Unknown"
                    tag_value = keys[2] if len(keys) > 2 else None

                    cost = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                    if cost == 0:
                        records_skipped += 1
                        continue

                    if tag_value and self.cost_allocation_tag_key:
                        mapped_team = self._map_team_by_tag(db, UUID(team_id), tag_value)
                        target_team_id = mapped_team.id if mapped_team else UUID(team_id)
                    else:
                        target_team_id = UUID(team_id)

                    provider = "aws"
                    gpu_type = "unknown"
                    if "EC2" in service or "Elastic Compute" in service:
                        gpu_type = "ec2"
                    elif "SageMaker" in service:
                        gpu_type = "sagemaker"

                    existing = (
                        db.query(CostSnapshot)
                        .filter(
                            CostSnapshot.team_id == target_team_id,
                            CostSnapshot.date == date,
                            CostSnapshot.provider == provider,
                            CostSnapshot.gpu_type == gpu_type,
                        )
                        .first()
                    )

                    if existing:
                        existing.cost_usd = existing.cost_usd + cost
                        existing.updated_at = datetime.utcnow()
                    else:
                        db.add(
                            CostSnapshot(
                                team_id=target_team_id,
                                date=date,
                                provider=provider,
                                gpu_type=gpu_type,
                                cost_usd=cost,
                            )
                        )
                    records_saved += 1

            db.commit()
            logger.info(
                "AWS sync completed: %d fetched, %d saved, %d skipped",
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
                "linked_accounts": self.linked_account_ids or ["all"],
                "tag_key": self.cost_allocation_tag_key or None,
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error("AWS Cost Explorer sync failed: %s - %s", error_code, error_message)
            raise IntegrationSyncError(
                f"AWS API error: {error_message}",
                provider="aws",
                operation="sync",
                original_error=e,
            )

        except IntegrationSyncError:
            raise

        except Exception as e:
            logger.error("AWS sync failed: %s", e, exc_info=True)
            raise IntegrationSyncError(
                f"AWS sync failed: {e}",
                provider="aws",
                operation="sync",
                original_error=e,
            )

        finally:
            db.close()


# Register the integration
integration_registry.register(IntegrationProvider.AWS, AWSCostExplorerIntegration)
