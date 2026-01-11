"""Demo seed endpoint for Heliox-AI."""
import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import verify_admin_api_key
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job
from app.models.team import Team
from app.services.cost_ingestion import CostIngestionService
from app.services.job_ingestion import JobIngestionService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class SeedResponse(BaseModel):
    """Response schema for seed operation."""
    
    status: str
    message: str
    results: dict


@router.post(
    "/seed",
    response_model=SeedResponse,
    status_code=status.HTTP_200_OK,
    summary="Seed database with demo data",
    description="Clears and re-seeds database with mock data. DEV ONLY - Requires ENV=dev.",
)
def seed_demo_data(
    *,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key),
) -> Any:
    """
    Seed database with demo data for presentations and testing.
    
    This endpoint:
    1. Verifies ENV=dev (safety check)
    2. Clears existing data from relevant tables
    3. Re-ingests mock cost data
    4. Re-ingests mock job data (creates teams)
    5. Generates UsageSnapshot data from jobs
    6. Returns summary of seeded data
    
    Safety Features:
    - Only works when ENV=dev
    - Requires X-API-Key header (admin authentication)
    - Does not drop tables or schema
    - Does not affect user accounts
    - Reversible (can re-run safely)
    
    Use Case:
    - Preparing for demos
    - Resetting test environment
    - Ensuring consistent starting state
    
    Returns:
        SeedResponse with operation summary
        
    Raises:
        403 Forbidden: If ENV is not 'dev'
        401 Unauthorized: If API key is invalid
        500 Internal Server Error: If seeding fails
    """
    # Safety check: Only allow in dev environment
    if settings.ENV != "dev":
        logger.warning(
            f"Demo seed attempted in non-dev environment: {settings.ENV}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Demo seed is only available in dev environment. Current: {settings.ENV}",
        )
    
    logger.info("Starting demo data seed operation")
    
    try:
        results = {
            "steps_completed": [],
            "steps_failed": []
        }
        
        # Step 1: Clear existing data (in correct order due to foreign keys)
        try:
            logger.info("Step 1: Clearing existing demo data...")
            
            # Clear usage snapshots (no foreign keys)
            usage_deleted = db.execute(delete(UsageSnapshot)).rowcount
            results["usage_snapshots_deleted"] = usage_deleted
            logger.info(f"Deleted {usage_deleted} usage snapshots")
            
            # Clear cost snapshots (no foreign keys)
            cost_deleted = db.execute(delete(CostSnapshot)).rowcount
            results["cost_snapshots_deleted"] = cost_deleted
            logger.info(f"Deleted {cost_deleted} cost snapshots")
            
            # Clear jobs (has foreign key to teams)
            jobs_deleted = db.execute(delete(Job)).rowcount
            results["jobs_deleted"] = jobs_deleted
            logger.info(f"Deleted {jobs_deleted} jobs")
            
            # Clear teams (referenced by jobs)
            teams_deleted = db.execute(delete(Team)).rowcount
            results["teams_deleted"] = teams_deleted
            logger.info(f"Deleted {teams_deleted} teams")
            
            db.commit()
            logger.info("Existing data cleared successfully")
            results["steps_completed"].append("clear_existing_data")
        except Exception as e:
            logger.error(f"Failed to clear existing data: {e}")
            results["steps_failed"].append({"step": "clear_existing_data", "error": str(e)})
            db.rollback()
            raise
        
        # Step 2: Ingest cost data
        try:
            logger.info("Step 2: Ingesting mock cost data...")
            from app.api.routes.admin import ingest_mock_cost_data
            
            cost_response = ingest_mock_cost_data(db=db, api_key=api_key)
            cost_result = cost_response.result if hasattr(cost_response, 'result') else cost_response
            results["cost_ingestion"] = {
                "inserted": cost_result.inserted if hasattr(cost_result, 'inserted') else cost_result.get("inserted", 0),
                "updated": cost_result.updated if hasattr(cost_result, 'updated') else cost_result.get("updated", 0),
                "failed": cost_result.failed if hasattr(cost_result, 'failed') else cost_result.get("failed", 0),
                "total": cost_result.total_records if hasattr(cost_result, 'total_records') else cost_result.get("total_records", 0),
            }
            logger.info(
                f"Cost ingestion complete: {results['cost_ingestion']['inserted']} inserted, "
                f"{results['cost_ingestion']['updated']} updated"
            )
            results["steps_completed"].append("ingest_cost_data")
        except Exception as e:
            logger.error(f"Failed to ingest cost data: {e}")
            results["steps_failed"].append({"step": "ingest_cost_data", "error": str(e)})
            results["cost_ingestion"] = {"inserted": 0, "updated": 0, "failed": 0, "total": 0}
            # Continue with other steps
        
        # Step 3: Ingest job data
        try:
            logger.info("Step 3: Ingesting mock job data...")
            from app.api.routes.admin import ingest_mock_job_data
            
            job_response = ingest_mock_job_data(db=db, api_key=api_key)
            job_result = job_response.result if hasattr(job_response, 'result') else job_response
            results["job_ingestion"] = {
                "teams_created": job_result.get("teams", {}).get("created", 0),
                "jobs_inserted": job_result.get("jobs", {}).get("inserted", 0),
                "jobs_updated": job_result.get("jobs", {}).get("updated", 0),
                "jobs_failed": job_result.get("jobs", {}).get("failed", 0),
            }
            logger.info(
                f"Job ingestion complete: {results['job_ingestion']['teams_created']} teams, "
                f"{results['job_ingestion']['jobs_inserted']} jobs inserted"
            )
            results["steps_completed"].append("ingest_job_data")
        except Exception as e:
            logger.error(f"Failed to ingest job data: {e}")
            results["steps_failed"].append({"step": "ingest_job_data", "error": str(e)})
            results["job_ingestion"] = {"teams_created": 0, "jobs_inserted": 0, "jobs_updated": 0, "jobs_failed": 0}
            # Continue with other steps
        
        # Step 4: Generate usage snapshots from jobs
        try:
            logger.info("Step 4: Generating usage snapshots from job data...")
            usage_count = _generate_usage_snapshots(db)
            results["usage_snapshots_generated"] = usage_count
            logger.info(f"Generated {usage_count} usage snapshots")
            results["steps_completed"].append("generate_usage_snapshots")
        except Exception as e:
            logger.error(f"Failed to generate usage snapshots: {e}")
            results["steps_failed"].append({"step": "generate_usage_snapshots", "error": str(e)})
            results["usage_snapshots_generated"] = 0
            # Continue to summary
        
        # Step 5: Get summary statistics
        try:
            logger.info("Step 5: Getting summary statistics...")
            summary = _get_data_summary(db)
            results["summary"] = summary
            results["steps_completed"].append("get_summary")
        except Exception as e:
            logger.error(f"Failed to get summary: {e}")
            results["steps_failed"].append({"step": "get_summary", "error": str(e)})
            results["summary"] = {"teams": 0, "jobs": 0, "cost_snapshots": 0, "usage_snapshots": 0}
        
        # Determine overall status
        if len(results["steps_failed"]) == 0:
            status = "success"
            logger.info("Demo data seed operation completed successfully")
        elif len(results["steps_completed"]) > 0:
            status = "partial_success"
            logger.warning(f"Demo data seed completed with {len(results['steps_failed'])} failed steps")
        else:
            status = "failed"
            logger.error("Demo data seed operation failed")
        
        message_parts = []
        if results.get("job_ingestion", {}).get("teams_created", 0) > 0:
            message_parts.append(f"{results['job_ingestion']['teams_created']} teams")
        if results.get("job_ingestion", {}).get("jobs_inserted", 0) > 0:
            message_parts.append(f"{results['job_ingestion']['jobs_inserted']} jobs")
        if results.get("cost_ingestion", {}).get("total", 0) > 0:
            message_parts.append(f"{results['cost_ingestion']['total']} cost snapshots")
        if results.get("usage_snapshots_generated", 0) > 0:
            message_parts.append(f"{results['usage_snapshots_generated']} usage snapshots")
        
        message = f"Demo data seeded successfully! {', '.join(message_parts)} created." if message_parts else "Demo data seed completed."
        
        if results["steps_failed"]:
            message += f" Note: {len(results['steps_failed'])} step(s) failed. Check results for details."
        
        return SeedResponse(
            status=status,
            message=message,
            results=results,
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error during demo data seed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed demo data: {str(e)}",
        )


def _generate_usage_snapshots(db: Session) -> int:
    """
    Generate UsageSnapshot records from Job data.
    
    For each day and (provider, gpu_type) combination, calculates
    total GPU hours from jobs that ran on that day.
    
    Args:
        db: Database session
        
    Returns:
        Number of usage snapshots created
    """
    from datetime import date, timedelta
    from decimal import Decimal
    
    # Get date range from existing jobs
    date_range_stmt = select(
        func.min(func.date(Job.start_time)).label("min_date"),
        func.max(func.date(Job.end_time)).label("max_date"),
    )
    result = db.execute(date_range_stmt).first()
    
    if not result or not result.min_date or not result.max_date:
        logger.warning("No jobs found to generate usage snapshots")
        return 0
    
    start_date = result.min_date
    end_date = result.max_date
    
    logger.info(f"Generating usage snapshots from {start_date} to {end_date}")
    
    current_date = start_date
    created_count = 0
    
    while current_date <= end_date:
        # Calculate total GPU hours per (provider, gpu_type) for this date
        # Jobs contribute hours for each day they span
        stmt = (
            select(
                Job.provider,
                Job.gpu_type,
                func.sum(
                    func.extract(
                        'epoch',
                        func.least(Job.end_time, current_date + timedelta(days=1)) -
                        func.greatest(Job.start_time, current_date)
                    ) / 3600
                ).label('total_hours')
            )
            .where(
                Job.start_time.isnot(None),
                Job.end_time.isnot(None),
                func.date(Job.start_time) <= current_date,
                func.date(Job.end_time) >= current_date
            )
            .group_by(Job.provider, Job.gpu_type)
        )
        
        daily_usage = db.execute(stmt).all()
        
        for provider, gpu_type, total_hours in daily_usage:
            if total_hours and total_hours > 0:
                usage = UsageSnapshot(
                    date=current_date,
                    provider=provider.lower(),
                    gpu_type=gpu_type.lower(),
                    gpu_hours=Decimal(str(round(total_hours, 2)))
                )
                db.add(usage)
                created_count += 1
        
        current_date += timedelta(days=1)
    
    db.commit()
    return created_count


def _get_data_summary(db: Session) -> dict:
    """
    Get summary statistics of seeded data.
    
    Args:
        db: Database session
        
    Returns:
        Dictionary with counts of all seeded entities
    """
    return {
        "teams": db.execute(select(func.count(Team.id))).scalar_one(),
        "jobs": db.execute(select(func.count(Job.id))).scalar_one(),
        "cost_snapshots": db.execute(select(func.count(CostSnapshot.id))).scalar_one(),
        "usage_snapshots": db.execute(select(func.count(UsageSnapshot.id))).scalar_one(),
    }


@router.get(
    "/status",
    summary="Get demo environment status",
    description="Check if demo mode is available and view current data counts.",
)
def get_demo_status(
    db: Session = Depends(get_db),
) -> Any:
    """
    Get demo environment status and data counts.
    
    Returns:
        Status information including environment and data counts
    """
    summary = _get_data_summary(db)
    
    return {
        "environment": settings.ENV,
        "demo_mode_available": settings.ENV == "dev",
        "data": summary,
    }

