"""Celery tasks for integration syncs."""
import logging
from datetime import datetime
from uuid import UUID

from celery import Task

from app.celery_app import celery_app
from app.core.db import get_db
from app.integrations.base import IntegrationProvider, IntegrationStatus, SyncStatus
from app.integrations.encryption import get_encryption
from app.integrations.models import IntegrationConnection, IntegrationSyncRun
from app.integrations.registry import integration_registry

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def run_integration_sync(self, connection_id: str, sync_run_id: str):
    """
    Run integration sync in background.
    
    Args:
        connection_id: Integration connection ID
        sync_run_id: Sync run ID to update
    """
    logger.info(f"Starting integration sync for connection {connection_id}, run {sync_run_id}")
    
    db = next(get_db())
    
    try:
        # Get connection and sync run
        connection = db.query(IntegrationConnection).filter(
            IntegrationConnection.id == UUID(connection_id)
        ).first()
        
        if not connection:
            logger.error(f"Connection {connection_id} not found")
            return
        
        sync_run = db.query(IntegrationSyncRun).filter(
            IntegrationSyncRun.id == UUID(sync_run_id)
        ).first()
        
        if not sync_run:
            logger.error(f"Sync run {sync_run_id} not found")
            return
        
        # Get integration class
        provider = IntegrationProvider(connection.provider)
        integration_class = integration_registry.get(provider)
        
        if not integration_class:
            error_msg = f"Integration provider {provider.value} not available"
            logger.error(error_msg)
            sync_run.status = SyncStatus.FAILED
            sync_run.error = error_msg
            sync_run.finished_at = datetime.utcnow()
            db.commit()
            return
        
        # Decrypt config and create integration instance
        encryption = get_encryption()
        decrypted_config = encryption.decrypt_config(connection.config_encrypted)
        integration = integration_class(decrypted_config)
        
        # Run sync (need to await async function)
        try:
            import asyncio
            metrics = asyncio.run(integration.sync(
                team_id=str(connection.team_id),
                last_sync_at=connection.last_successful_sync_at
            ))
            
            # Update sync run
            sync_run.status = SyncStatus.SUCCESS
            sync_run.metrics_json = metrics
            sync_run.finished_at = datetime.utcnow()
            
            # Update connection
            connection.status = IntegrationStatus.ACTIVE
            connection.last_sync_at = datetime.utcnow()
            connection.last_successful_sync_at = datetime.utcnow()
            connection.last_error = None
            
            # Record ingestion usage for billing
            records_saved = metrics.get("records_saved", 0) if metrics else 0
            if records_saved > 0:
                from app.utils.usage_metering import record_ingestion_event
                try:
                    record_ingestion_event(
                        team_id=connection.team_id,
                        line_items_count=records_saved,
                        source=provider.value,
                        db=db
                    )
                    logger.debug(f"Recorded ingestion usage: {records_saved} line items from {provider.value}")
                except Exception as usage_error:
                    logger.error(f"Failed to record ingestion usage: {usage_error}")
            
            logger.info(f"Integration sync completed successfully for {connection_id}")
        
        except Exception as sync_error:
            logger.error(f"Integration sync failed for {connection_id}: {sync_error}", exc_info=True)
            
            # Update sync run
            sync_run.status = SyncStatus.FAILED
            sync_run.error = str(sync_error)
            sync_run.error_details = {"error_type": type(sync_error).__name__}
            sync_run.finished_at = datetime.utcnow()
            
            # Update connection
            connection.status = IntegrationStatus.ERROR
            connection.last_error = str(sync_error)
            connection.last_sync_at = datetime.utcnow()
        
        db.commit()
    
    except Exception as e:
        logger.error(f"Critical error in integration sync task: {e}", exc_info=True)
        # Try to update sync run if possible
        try:
            sync_run = db.query(IntegrationSyncRun).filter(
                IntegrationSyncRun.id == UUID(sync_run_id)
            ).first()
            if sync_run:
                sync_run.status = SyncStatus.FAILED
                sync_run.error = f"Critical error: {str(e)}"
                sync_run.finished_at = datetime.utcnow()
                db.commit()
        except:
            pass
    
    finally:
        db.close()


@celery_app.task
def run_scheduled_syncs():
    """
    Run scheduled syncs for all enabled integrations.
    
    This task should be scheduled to run periodically (e.g., every 5 minutes)
    and will trigger syncs for connections that are due based on their sync_interval_minutes.
    """
    logger.info("Running scheduled integration syncs")
    
    db = next(get_db())
    
    try:
        # Find connections that need syncing
        now = datetime.utcnow()
        
        # Query for connections where:
        # - auto_sync_enabled = True
        # - status = ACTIVE
        # - last_sync_at is None OR (now - last_sync_at) >= sync_interval_minutes
        
        connections = db.query(IntegrationConnection).filter(
            IntegrationConnection.auto_sync_enabled == True,
            IntegrationConnection.status == IntegrationStatus.ACTIVE
        ).all()
        
        synced_count = 0
        
        for connection in connections:
            # Check if sync is due
            if connection.last_sync_at is None:
                should_sync = True
            else:
                minutes_since_sync = (now - connection.last_sync_at).total_seconds() / 60
                should_sync = minutes_since_sync >= connection.sync_interval_minutes
            
            if should_sync:
                # Create sync run
                sync_run = IntegrationSyncRun(
                    connection_id=connection.id,
                    started_at=now,
                    status=SyncStatus.RUNNING,
                    triggered_by="scheduled"
                )
                db.add(sync_run)
                db.commit()
                db.refresh(sync_run)
                
                # Trigger async task
                run_integration_sync.delay(str(connection.id), str(sync_run.id))
                synced_count += 1
                
                logger.info(f"Scheduled sync for connection {connection.id}")
        
        logger.info(f"Scheduled {synced_count} integration syncs")
    
    except Exception as e:
        logger.error(f"Error in scheduled syncs task: {e}", exc_info=True)
    
    finally:
        db.close()
