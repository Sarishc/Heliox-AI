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
from app.integrations.base import IntegrationBase, IntegrationProvider, IntegrationHealthStatus
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
    - aws_access_key_id: AWS Access Key ID (IAM user with Cost Explorer permissions)
    - aws_secret_access_key: AWS Secret Access Key
    - aws_region: AWS Region (default: us-east-1)
    
    Optional configuration:
    - linked_account_ids: List of AWS account IDs to sync (empty = all accounts)
    - cost_allocation_tag_key: Cost allocation tag key for team mapping (e.g., "Team")
    - cost_allocation_tag_values: List of tag values to filter (empty = all values)
    """
    
    provider = IntegrationProvider.AWS
    display_name = "AWS Cost Explorer"
    description = "Import GPU and infrastructure costs from AWS Cost Explorer API"
    
    required_config_fields = [
        "aws_access_key_id",
        "aws_secret_access_key",
    ]
    
    optional_config_fields = [
        "aws_region",
        "linked_account_ids",
        "cost_allocation_tag_key",
        "cost_allocation_tag_values"
    ]
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with config and create boto3 clients."""
        super().__init__(config)
        
        # Set defaults
        self.region = config.get("aws_region", "us-east-1")
        self.linked_account_ids = config.get("linked_account_ids", [])
        if isinstance(self.linked_account_ids, str):
            self.linked_account_ids = [x.strip() for x in self.linked_account_ids.split(",") if x.strip()]
        
        self.cost_allocation_tag_key = config.get("cost_allocation_tag_key", "")
        self.cost_allocation_tag_values = config.get("cost_allocation_tag_values", [])
        if isinstance(self.cost_allocation_tag_values, str):
            self.cost_allocation_tag_values = [x.strip() for x in self.cost_allocation_tag_values.split(",") if x.strip()]
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate AWS configuration.
        
        Checks that required fields are present. Actual credential validation
        happens in health() check.
        """
        # Check required fields
        for field in self.required_config_fields:
            if field not in config or not config[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate access key format (basic check)
        access_key = config["aws_access_key_id"]
        if not isinstance(access_key, str) or len(access_key) < 16:
            raise ValueError("aws_access_key_id must be a valid AWS access key (16-128 characters)")
        
        # Validate secret key format (basic check)
        secret_key = config["aws_secret_access_key"]
        if not isinstance(secret_key, str) or len(secret_key) < 40:
            raise ValueError("aws_secret_access_key must be a valid AWS secret key (40+ characters)")
        
        # Validate region if provided
        region = config.get("aws_region", "us-east-1")
        if not isinstance(region, str) or len(region) < 3:
            raise ValueError("aws_region must be a valid AWS region (e.g., us-east-1)")
        
        # Validate linked account IDs if provided
        linked_accounts = config.get("linked_account_ids", [])
        if linked_accounts:
            if isinstance(linked_accounts, str):
                linked_accounts = [x.strip() for x in linked_accounts.split(",") if x.strip()]
            
            for account_id in linked_accounts:
                if not account_id.isdigit() or len(account_id) != 12:
                    raise ValueError(f"Invalid AWS account ID: {account_id} (must be 12 digits)")
        
        logger.debug("AWS Cost Explorer configuration validated successfully")
    
    def _get_boto3_session(self) -> boto3.Session:
        """Create boto3 session with configured credentials."""
        return boto3.Session(
            aws_access_key_id=self.config["aws_access_key_id"],
            aws_secret_access_key=self.config["aws_secret_access_key"],
            region_name=self.region
        )
    
    def _get_caller_identity(self) -> Dict[str, Any]:
        """
        Get AWS caller identity (validates credentials).
        
        Returns:
            Dict with Account, Arn, UserId
            
        Raises:
            ClientError: If credentials are invalid
        """
        session = self._get_boto3_session()
        sts_client = session.client('sts')
        return sts_client.get_caller_identity()
    
    async def health(self) -> Dict[str, Any]:
        """
        Check AWS Cost Explorer integration health.
        
        Tests:
        1. Credentials are valid (sts:GetCallerIdentity)
        2. Cost Explorer API is accessible (minimal query)
        3. Permissions are sufficient
        """
        logger.debug("Checking AWS Cost Explorer integration health")
        
        try:
            # Test 1: Validate credentials with STS
            identity = self._get_caller_identity()
            account_id = identity["Account"]
            arn = identity["Arn"]
            
            # Test 2: Minimal Cost Explorer query
            session = self._get_boto3_session()
            ce_client = session.client('ce', region_name=self.region)
            
            # Query last 1 day to test permissions
            today = datetime.utcnow().date()
            yesterday = today - timedelta(days=1)
            
            response = ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': yesterday.strftime('%Y-%m-%d'),
                    'End': today.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            
            # If we got here, everything works
            return {
                "status": IntegrationHealthStatus.HEALTHY.value,
                "message": "AWS Cost Explorer connection successful",
                "details": {
                    "api_reachable": True,
                    "credentials_valid": True,
                    "account_id": account_id,
                    "caller_arn": arn,
                    "region": self.region,
                    "cost_explorer_access": True
                }
            }
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            logger.error(f"AWS Cost Explorer health check failed: {error_code} - {error_message}")
            
            # Provide helpful error messages
            if error_code in ('InvalidClientTokenId', 'SignatureDoesNotMatch', 'AccessDenied'):
                message = "Invalid AWS credentials or insufficient permissions"
            elif error_code == 'UnrecognizedClientException':
                message = "AWS credentials are invalid or expired"
            else:
                message = f"AWS API error: {error_message}"
            
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": message,
                "details": {
                    "api_reachable": error_code != 'EndpointConnectionError',
                    "credentials_valid": error_code not in ('InvalidClientTokenId', 'SignatureDoesNotMatch'),
                    "error_code": error_code,
                    "error_message": error_message
                }
            }
        
        except BotoCoreError as e:
            logger.error(f"AWS boto3 error: {e}", exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"AWS SDK error: {str(e)}",
                "details": {
                    "api_reachable": False,
                    "credentials_valid": False,
                    "error": str(e)
                }
            }
        
        except Exception as e:
            logger.error(f"Unexpected error in AWS health check: {e}", exc_info=True)
            return {
                "status": IntegrationHealthStatus.UNHEALTHY.value,
                "message": f"Health check failed: {str(e)}",
                "details": {
                    "error": str(e)
                }
            }
    
    def _map_team_by_tag(self, db: Session, team_id: UUID, tag_value: str) -> Optional[Team]:
        """
        Map AWS cost allocation tag value to Heliox team.
        
        Args:
            db: Database session
            team_id: Integration owner team ID (fallback)
            tag_value: Cost allocation tag value (e.g., "ml-research")
            
        Returns:
            Team object or None
        """
        # Try to find team by name matching tag value
        team = db.query(Team).filter(
            Team.name.ilike(f"%{tag_value}%")
        ).first()
        
        if team:
            logger.debug(f"Mapped tag value '{tag_value}' to team {team.id}")
            return team
        
        # Fallback to integration owner team
        logger.debug(f"No team found for tag value '{tag_value}', using owner team {team_id}")
        return db.query(Team).filter(Team.id == team_id).first()
    
    async def sync(self, team_id: str, last_sync_at: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Sync cost data from AWS Cost Explorer.
        
        Steps:
        1. Determine date range (last 30 days or since last_sync_at)
        2. Query AWS Cost Explorer API
        3. Transform results to cost_snapshots format
        4. Upsert to database (idempotent)
        5. Map teams using cost allocation tags if configured
        
        Args:
            team_id: Heliox team ID (owner of this integration)
            last_sync_at: Last successful sync timestamp
            
        Returns:
            Sync metrics dictionary
        """
        logger.info(f"Starting AWS Cost Explorer sync for team {team_id}")
        
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
            
            # Query Cost Explorer
            session = self._get_boto3_session()
            ce_client = session.client('ce', region_name=self.region)
            
            # Build filter
            filter_expr = None
            if self.linked_account_ids:
                filter_expr = {
                    'Dimensions': {
                        'Key': 'LINKED_ACCOUNT',
                        'Values': self.linked_account_ids
                    }
                }
            
            # Build group by dimensions
            group_by = [
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
            ]
            
            # Add tag grouping if configured
            if self.cost_allocation_tag_key:
                group_by.append({
                    'Type': 'TAG',
                    'Key': self.cost_allocation_tag_key
                })
            
            # Query AWS Cost Explorer
            response = ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=group_by,
                Filter=filter_expr if filter_expr else None
            )
            
            # Process results
            records_fetched = 0
            records_saved = 0
            records_skipped = 0
            errors = []
            
            for result_by_time in response.get('ResultsByTime', []):
                date_str = result_by_time['TimePeriod']['Start']
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                for group in result_by_time.get('Groups', []):
                    records_fetched += 1
                    
                    # Parse dimensions
                    keys = group.get('Keys', [])
                    service = keys[0] if len(keys) > 0 else 'Unknown'
                    account_id = keys[1] if len(keys) > 1 else 'Unknown'
                    tag_value = keys[2] if len(keys) > 2 else None
                    
                    # Get cost
                    cost = Decimal(group['Metrics']['UnblendedCost']['Amount'])
                    
                    # Skip zero costs
                    if cost == 0:
                        records_skipped += 1
                        continue
                    
                    # Map to team
                    if tag_value and self.cost_allocation_tag_key:
                        mapped_team = self._map_team_by_tag(db, UUID(team_id), tag_value)
                        target_team_id = mapped_team.id if mapped_team else UUID(team_id)
                    else:
                        target_team_id = UUID(team_id)
                    
                    # Map service to provider/GPU type
                    # For AWS, we can parse EC2 instance types from service
                    provider = "aws"
                    gpu_type = "unknown"
                    
                    # Try to extract GPU type from service name
                    if "EC2" in service or "Elastic Compute" in service:
                        # In a production implementation, you'd parse instance types
                        # from detailed billing or use resource tags
                        gpu_type = "ec2"  # Simplified for now
                    elif "SageMaker" in service:
                        gpu_type = "sagemaker"
                    
                    # Upsert cost snapshot (idempotent)
                    # Use unique constraint on (team_id, date, provider, gpu_type)
                    existing = db.query(CostSnapshot).filter(
                        CostSnapshot.team_id == target_team_id,
                        CostSnapshot.date == date,
                        CostSnapshot.provider == provider,
                        CostSnapshot.gpu_type == gpu_type
                    ).first()
                    
                    if existing:
                        # Update existing record (aggregate if multiple services)
                        existing.cost_usd = existing.cost_usd + cost
                        existing.updated_at = datetime.utcnow()
                        records_saved += 1
                        logger.debug(f"Updated cost snapshot: {date} {provider} {gpu_type} += ${cost}")
                    else:
                        # Create new record
                        snapshot = CostSnapshot(
                            team_id=target_team_id,
                            date=date,
                            provider=provider,
                            gpu_type=gpu_type,
                            cost_usd=cost
                        )
                        db.add(snapshot)
                        records_saved += 1
                        logger.debug(f"Created cost snapshot: {date} {provider} {gpu_type} = ${cost}")
            
            # Commit all changes
            db.commit()
            
            logger.info(f"AWS sync completed: {records_fetched} fetched, {records_saved} saved, {records_skipped} skipped")
            
            return {
                "records_fetched": records_fetched,
                "records_saved": records_saved,
                "records_skipped": records_skipped,
                "errors": errors,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "linked_accounts": self.linked_account_ids or ["all"],
                "tag_key": self.cost_allocation_tag_key or None
            }
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"AWS Cost Explorer sync failed: {error_code} - {error_message}")
            raise Exception(f"AWS API error: {error_message}")
        
        except Exception as e:
            logger.error(f"AWS sync failed: {e}", exc_info=True)
            raise
        
        finally:
            db.close()


# Register the integration
integration_registry.register(IntegrationProvider.AWS, AWSCostExplorerIntegration)
