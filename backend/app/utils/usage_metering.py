"""Usage metering utility for tracking billable usage."""
import logging
import random
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.usage import UsageEvent, UsageEventType

logger = logging.getLogger(__name__)
settings = get_settings()


def record_usage_event(
    team_id: UUID,
    event_type: UsageEventType,
    quantity: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None
) -> None:
    """
    Record a usage event for billing purposes.
    
    Args:
        team_id: Team UUID
        event_type: Type of usage event
        quantity: Quantity of usage (default: 1)
        metadata: Optional metadata dictionary
        db: Optional database session (will create if not provided)
    
    Returns:
        None (logs errors but doesn't raise to avoid breaking main flow)
    """
    try:
        # Get database session
        should_close = False
        if db is None:
            db = next(get_db())
            should_close = True
        
        # Create usage event
        usage_event = UsageEvent(
            team_id=team_id,
            event_type=event_type,
            quantity=quantity,
            event_metadata=metadata or {}
        )
        
        db.add(usage_event)
        db.commit()
        
        logger.debug(
            f"Recorded usage event: team={team_id}, type={event_type.value}, "
            f"quantity={quantity}"
        )
        
        # Close session if we created it
        if should_close:
            db.close()
    
    except Exception as e:
        logger.error(f"Failed to record usage event: {e}", exc_info=True)
        # Don't raise - usage metering shouldn't break the main flow


def should_sample_request(sample_rate: float = 1.0) -> bool:
    """
    Determine if request should be sampled based on sample rate.
    
    Args:
        sample_rate: Probability of sampling (0.0 to 1.0)
        
    Returns:
        True if request should be sampled
    """
    if sample_rate >= 1.0:
        return True
    if sample_rate <= 0.0:
        return False
    
    return random.random() < sample_rate


def record_api_request(
    team_id: UUID,
    method: str,
    path: str,
    status_code: int,
    sample_rate: float = 1.0,
    db: Optional[Session] = None
) -> None:
    """
    Record an API request usage event.
    
    Args:
        team_id: Team UUID
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP status code
        sample_rate: Sampling rate (0.0 to 1.0)
        db: Optional database session
    """
    # Sample requests to reduce write volume
    if not should_sample_request(sample_rate):
        return
    
    # Calculate actual quantity based on sample rate
    # If sampling at 10%, each sampled request counts as 10
    quantity = int(1 / sample_rate) if sample_rate > 0 else 1
    
    metadata = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    record_usage_event(
        team_id=team_id,
        event_type=UsageEventType.API_REQUEST,
        quantity=quantity,
        metadata=metadata,
        db=db
    )


def record_ingestion_event(
    team_id: UUID,
    line_items_count: int,
    source: str,
    db: Optional[Session] = None
) -> None:
    """
    Record a data ingestion usage event.
    
    Args:
        team_id: Team UUID
        line_items_count: Number of cost line items processed
        source: Data source (e.g., "aws", "gcp", "csv")
        db: Optional database session
    """
    metadata = {
        "source": source,
        "line_items": line_items_count,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    record_usage_event(
        team_id=team_id,
        event_type=UsageEventType.INGESTION,
        quantity=line_items_count,
        metadata=metadata,
        db=db
    )


def record_seat_snapshot(
    team_id: UUID,
    active_users_count: int,
    db: Optional[Session] = None
) -> None:
    """
    Record a daily seat count snapshot.
    
    Args:
        team_id: Team UUID
        active_users_count: Number of active users
        db: Optional database session
    """
    metadata = {
        "active_users": active_users_count,
        "snapshot_date": datetime.utcnow().date().isoformat()
    }
    
    record_usage_event(
        team_id=team_id,
        event_type=UsageEventType.SEAT,
        quantity=active_users_count,
        metadata=metadata,
        db=db
    )


def record_gpu_node_snapshot(
    team_id: UUID,
    gpu_nodes_count: int,
    db: Optional[Session] = None
) -> None:
    """
    Record a daily GPU node count snapshot.
    
    Args:
        team_id: Team UUID
        gpu_nodes_count: Number of monitored GPU nodes
        db: Optional database session
    """
    metadata = {
        "gpu_nodes": gpu_nodes_count,
        "snapshot_date": datetime.utcnow().date().isoformat()
    }
    
    record_usage_event(
        team_id=team_id,
        event_type=UsageEventType.GPU_NODE,
        quantity=gpu_nodes_count,
        metadata=metadata,
        db=db
    )
