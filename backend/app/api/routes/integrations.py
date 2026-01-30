"""API routes for integrations."""
import logging
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.integrations.base import IntegrationProvider, IntegrationStatus, SyncStatus
from app.integrations.encryption import get_encryption
from app.integrations.models import IntegrationConnection, IntegrationSyncRun
from app.integrations.registry import integration_registry
from app.models.team_api_key import TeamAPIKey
from app.schemas.integrations import (
    IntegrationConnectionCreate,
    IntegrationConnectionResponse,
    IntegrationHealthResponse,
    IntegrationListResponse,
    IntegrationSyncRunResponse,
    AvailableIntegrationResponse
)

router = APIRouter()
logger = logging.getLogger(__name__)


# AWS-specific routes
@router.post("/aws/test")
async def test_aws_credentials(
    *,
    config: Dict[str, Any],
    api_key: TeamAPIKey = Depends(verify_team_api_key)
):
    """
    Test AWS credentials before saving.
    
    Validates credentials by calling:
    1. sts:GetCallerIdentity (verify credentials)
    2. ce:GetCostAndUsage (minimal query to verify Cost Explorer access)
    
    Returns account info and validation results.
    """
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration
    
    try:
        # Create integration instance
        integration = AWSCostExplorerIntegration(config)
        
        # Run health check
        health_result = await integration.health()
        
        return {
            "valid": health_result["status"] == "healthy",
            "account_id": health_result.get("details", {}).get("account_id"),
            "caller_arn": health_result.get("details", {}).get("caller_arn"),
            "message": health_result["message"],
            "details": health_result["details"]
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration: {str(e)}"
        )
    except Exception as e:
        logger.error(f"AWS credential test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Credential test failed: {str(e)}"
        )


@router.post("/aws/connect", response_model=IntegrationConnectionResponse, status_code=status.HTTP_201_CREATED)
async def connect_aws(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    connection_data: IntegrationConnectionCreate
):
    """
    Connect AWS Cost Explorer integration.
    
    This is a convenience endpoint that:
    1. Tests credentials
    2. Creates integration connection
    3. Triggers initial sync
    
    Equivalent to POST /integrations/connect with provider=aws but with
    additional validation and automatic initial sync.
    """
    from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration
    
    # Force provider to aws
    connection_data.provider = "aws"
    
    # Test credentials first
    try:
        integration = AWSCostExplorerIntegration(connection_data.config)
        health_result = await integration.health()
        
        if health_result["status"] != "healthy":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"AWS credentials test failed: {health_result['message']}"
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration: {str(e)}"
        )
    
    # Create connection using existing endpoint logic
    # (Reuse the create_integration_connection function)
    from app.integrations.encryption import get_encryption
    
    # Encrypt configuration
    encryption = get_encryption()
    encrypted_config = encryption.encrypt_config(connection_data.config)
    
    # Create connection
    connection = IntegrationConnection(
        team_id=api_key.team_id,
        provider=IntegrationProvider.AWS,
        name=connection_data.name,
        description=connection_data.description,
        config_encrypted=encrypted_config,
        status=IntegrationStatus.PENDING,
        auto_sync_enabled=connection_data.auto_sync_enabled,
        sync_interval_minutes=connection_data.sync_interval_minutes
    )
    
    db.add(connection)
    db.commit()
    db.refresh(connection)
    
    logger.info(f"Created AWS integration connection {connection.id} for team {api_key.team_id}")
    
    # Trigger initial sync
    from app.tasks.integration_tasks import run_integration_sync
    from app.integrations.models import IntegrationSyncRun
    from datetime import datetime
    
    sync_run = IntegrationSyncRun(
        connection_id=connection.id,
        started_at=datetime.utcnow(),
        status=SyncStatus.RUNNING,
        triggered_by="initial"
    )
    
    db.add(sync_run)
    db.commit()
    db.refresh(sync_run)
    
    # Trigger async sync
    run_integration_sync.delay(str(connection.id), str(sync_run.id))
    
    # Return response with masked config
    decrypted_config = encryption.decrypt_config(connection.config_encrypted)
    safe_config = integration.get_display_config(decrypted_config)
    
    return IntegrationConnectionResponse(
        id=connection.id,
        team_id=connection.team_id,
        provider=connection.provider.value,
        name=connection.name,
        description=connection.description,
        config=safe_config,
        status=connection.status.value,
        last_error=connection.last_error,
        last_sync_at=connection.last_sync_at,
        last_successful_sync_at=connection.last_successful_sync_at,
        auto_sync_enabled=connection.auto_sync_enabled,
        sync_interval_minutes=connection.sync_interval_minutes,
        created_at=connection.created_at,
        updated_at=connection.updated_at
    )


@router.get("/available", response_model=List[AvailableIntegrationResponse])
def list_available_integrations():
    """
    List all available integrations (both enabled and disabled).
    
    Returns list of integrations that can be configured, including:
    - Enabled integrations (ready to use)
    - Disabled integrations (coming soon)
    """
    available = integration_registry.list_available()
    return [AvailableIntegrationResponse(**item) for item in available]


@router.post("/connect", response_model=IntegrationConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_integration_connection(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    connection_create: IntegrationConnectionCreate
):
    """
    Create a new integration connection.
    
    Steps:
    1. Validate provider is supported
    2. Validate configuration using integration's validate_config()
    3. Encrypt configuration
    4. Save to database
    5. Perform initial health check
    """
    # Check if provider is supported
    provider = IntegrationProvider(connection_create.provider)
    integration_class = integration_registry.get(provider)
    
    if not integration_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration provider '{connection_create.provider}' is not available yet"
        )
    
    # Validate configuration
    try:
        integration = integration_class(connection_create.config)
        integration.validate_config(connection_create.config)
    except ValueError as e:
        logger.warning(f"Invalid integration config for {provider.value}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error validating integration config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate integration configuration"
        )
    
    # Encrypt configuration
    encryption = get_encryption()
    encrypted_config = encryption.encrypt_config(connection_create.config)
    
    # Create connection
    connection = IntegrationConnection(
        team_id=api_key.team_id,
        provider=provider,
        name=connection_create.name,
        description=connection_create.description,
        config_encrypted=encrypted_config,
        status=IntegrationStatus.PENDING,
        auto_sync_enabled=connection_create.auto_sync_enabled,
        sync_interval_minutes=connection_create.sync_interval_minutes
    )
    
    db.add(connection)
    db.commit()
    db.refresh(connection)
    
    logger.info(f"Created integration connection {connection.id} for team {api_key.team_id}")
    
    # Convert to response (decrypt config for display)
    decrypted_config = encryption.decrypt_config(connection.config_encrypted)
    safe_config = integration.get_display_config(decrypted_config)
    
    return IntegrationConnectionResponse(
        id=connection.id,
        team_id=connection.team_id,
        provider=connection.provider.value,
        name=connection.name,
        description=connection.description,
        config=safe_config,
        status=connection.status.value,
        last_error=connection.last_error,
        last_sync_at=connection.last_sync_at,
        last_successful_sync_at=connection.last_successful_sync_at,
        auto_sync_enabled=connection.auto_sync_enabled,
        sync_interval_minutes=connection.sync_interval_minutes,
        created_at=connection.created_at,
        updated_at=connection.updated_at
    )


@router.get("", response_model=IntegrationListResponse)
def list_integrations(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key)
):
    """
    List all integration connections for the authenticated team.
    """
    connections = db.query(IntegrationConnection).filter(
        IntegrationConnection.team_id == api_key.team_id
    ).all()
    
    encryption = get_encryption()
    result = []
    
    for connection in connections:
        # Get integration class for safe config display
        integration_class = integration_registry.get(IntegrationProvider(connection.provider))
        
        if integration_class:
            decrypted_config = encryption.decrypt_config(connection.config_encrypted)
            integration = integration_class(decrypted_config)
            safe_config = integration.get_display_config(decrypted_config)
        else:
            safe_config = {"error": "Integration not available"}
        
        result.append(IntegrationConnectionResponse(
            id=connection.id,
            team_id=connection.team_id,
            provider=connection.provider.value,
            name=connection.name,
            description=connection.description,
            config=safe_config,
            status=connection.status.value,
            last_error=connection.last_error,
            last_sync_at=connection.last_sync_at,
            last_successful_sync_at=connection.last_successful_sync_at,
            auto_sync_enabled=connection.auto_sync_enabled,
            sync_interval_minutes=connection.sync_interval_minutes,
            created_at=connection.created_at,
            updated_at=connection.updated_at
        ))
    
    return IntegrationListResponse(connections=result, total=len(result))


@router.post("/{connection_id}/sync", response_model=IntegrationSyncRunResponse)
async def trigger_sync(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    connection_id: UUID
):
    """
    Trigger a manual sync for an integration connection.
    
    This will:
    1. Validate connection exists and belongs to team
    2. Create a sync run record
    3. Trigger async Celery task to perform sync
    4. Return sync run details
    """
    # Get connection
    connection = db.query(IntegrationConnection).filter(
        IntegrationConnection.id == connection_id,
        IntegrationConnection.team_id == api_key.team_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration connection not found"
        )
    
    # Check if integration is available
    provider = IntegrationProvider(connection.provider)
    integration_class = integration_registry.get(provider)
    
    if not integration_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration provider '{connection.provider}' is not available"
        )
    
    # Create sync run
    sync_run = IntegrationSyncRun(
        connection_id=connection.id,
        started_at=datetime.utcnow(),
        status=SyncStatus.RUNNING,
        triggered_by="manual"
    )
    
    db.add(sync_run)
    db.commit()
    db.refresh(sync_run)
    
    # Trigger async Celery task
    from app.tasks.integration_tasks import run_integration_sync
    run_integration_sync.delay(str(connection.id), str(sync_run.id))
    
    logger.info(f"Triggered sync for connection {connection.id}, run {sync_run.id}")
    
    return IntegrationSyncRunResponse(
        id=sync_run.id,
        connection_id=sync_run.connection_id,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        status=sync_run.status.value,
        error=sync_run.error,
        metrics=sync_run.metrics_json,
        triggered_by=sync_run.triggered_by
    )


@router.get("/{connection_id}/health", response_model=IntegrationHealthResponse)
async def check_health(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    connection_id: UUID
):
    """
    Check health of an integration connection.
    
    Performs a health check by:
    1. Validating connection exists
    2. Decrypting configuration
    3. Calling integration's health() method
    """
    # Get connection
    connection = db.query(IntegrationConnection).filter(
        IntegrationConnection.id == connection_id,
        IntegrationConnection.team_id == api_key.team_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration connection not found"
        )
    
    # Check if integration is available
    provider = IntegrationProvider(connection.provider)
    integration_class = integration_registry.get(provider)
    
    if not integration_class:
        return IntegrationHealthResponse(
            connection_id=connection.id,
            status="unhealthy",
            message=f"Integration provider '{connection.provider}' is not available",
            details={}
        )
    
    # Decrypt config and create integration instance
    encryption = get_encryption()
    decrypted_config = encryption.decrypt_config(connection.config_encrypted)
    integration = integration_class(decrypted_config)
    
    # Perform health check
    try:
        health_result = await integration.health()
        
        return IntegrationHealthResponse(
            connection_id=connection.id,
            status=health_result.get("status", "unknown"),
            message=health_result.get("message", ""),
            details=health_result.get("details", {})
        )
    except Exception as e:
        logger.error(f"Health check failed for connection {connection.id}: {e}", exc_info=True)
        return IntegrationHealthResponse(
            connection_id=connection.id,
            status="unhealthy",
            message=f"Health check failed: {str(e)}",
            details={}
        )


@router.get("/{connection_id}/sync-history", response_model=List[IntegrationSyncRunResponse])
def get_sync_history(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    connection_id: UUID,
    limit: int = 10
):
    """
    Get sync history for an integration connection.
    """
    # Verify connection belongs to team
    connection = db.query(IntegrationConnection).filter(
        IntegrationConnection.id == connection_id,
        IntegrationConnection.team_id == api_key.team_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration connection not found"
        )
    
    # Get sync runs
    sync_runs = db.query(IntegrationSyncRun).filter(
        IntegrationSyncRun.connection_id == connection_id
    ).order_by(
        IntegrationSyncRun.started_at.desc()
    ).limit(limit).all()
    
    return [
        IntegrationSyncRunResponse(
            id=run.id,
            connection_id=run.connection_id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status.value,
            error=run.error,
            metrics=run.metrics_json,
            triggered_by=run.triggered_by
        )
        for run in sync_runs
    ]


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    connection_id: UUID
):
    """
    Delete an integration connection.
    
    This will also cascade delete all sync run history.
    """
    connection = db.query(IntegrationConnection).filter(
        IntegrationConnection.id == connection_id,
        IntegrationConnection.team_id == api_key.team_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration connection not found"
        )
    
    db.delete(connection)
    db.commit()
    
    logger.info(f"Deleted integration connection {connection_id} for team {api_key.team_id}")
    
    return None
