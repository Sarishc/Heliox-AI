"""Admin API endpoints for system management and data ingestion."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import verify_admin_api_key
from app.services.cost_ingestion import CostIngestionService, IngestionResult
from app.services.job_ingestion import JobIngestionService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class IngestionResponse(BaseModel):
    """Response schema for ingestion operations."""
    
    status: str
    message: str
    result: IngestionResult


@router.post(
    "/ingest/cost/mock",
    response_model=IngestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest mock cost data",
    description="Load and ingest mock AWS cost data from JSON file into the database. "
                "Performs idempotent upserts based on (date, provider, gpu_type). "
                "DEV ONLY - Requires ENV=dev.",
)
def ingest_mock_cost_data(
    *,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key),
) -> Any:
    """
    Ingest mock cost data into the database.
    
    Security: Only available in dev environment.
    
    This endpoint:
    1. Loads mock cost data from backend/app/data/mock_cost_export.json
    2. Validates the JSON structure and data types
    3. Normalizes provider and gpu_type strings (lowercase)
    4. Performs idempotent upserts to the cost_snapshots table
    5. Returns statistics on inserted/updated/failed records
    
    Authentication:
    - Requires X-API-Key header matching ADMIN_API_KEY environment variable
    
    Idempotency:
    - Records are upserted based on unique key (date, provider, gpu_type)
    - If record exists, only cost_usd is updated
    - Safe to run multiple times
    
    Returns:
        IngestionResponse with operation statistics
        
    Raises:
        400 Bad Request: If JSON is invalid or data validation fails
        401 Unauthorized: If API key is missing or invalid
        403 Forbidden: If ENV is not 'dev'
        500 Internal Server Error: If database operation fails
    """
    # Security: Only allow in dev environment
    if settings.ENV != "dev":
        logger.warning(
            f"Mock cost ingestion attempted in non-dev environment: {settings.ENV}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Mock ingestion is only available in dev environment. Current: {settings.ENV}",
        )
    
    try:
        logger.info("Starting mock cost data ingestion")
        
        # Initialize ingestion service
        ingestion_service = CostIngestionService(db)
        
        # Ingest data
        result = ingestion_service.ingest_cost_data()
        
        # Build response
        if result.failed > 0:
            # Partial success - some records failed
            logger.warning(
                f"Ingestion completed with errors: {result.failed} failed records"
            )
            return IngestionResponse(
                status="partial_success",
                message=f"Ingested {result.inserted + result.updated} records, "
                        f"{result.failed} failed. Check logs for details.",
                result=result,
            )
        else:
            # Full success
            logger.info(
                f"Ingestion successful: {result.inserted} inserted, "
                f"{result.updated} updated"
            )
            return IngestionResponse(
                status="success",
                message=f"Successfully ingested {result.total_records} cost records. "
                        f"{result.inserted} inserted, {result.updated} updated.",
                result=result,
            )
    
    except FileNotFoundError as e:
        logger.error(f"Cost data file not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cost data file not found: {str(e)}",
        )
    
    except ValidationError as e:
        logger.error(f"Cost data validation failed: {e}")
        # Extract user-friendly error messages
        errors = []
        for error in e.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            errors.append(f"{loc}: {error['msg']}")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Invalid cost data format",
                "errors": errors,
            },
        )
    
    except Exception as e:
        logger.error(f"Critical error during ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest cost data. Check server logs for details.",
        )


@router.post(
    "/ingest/jobs/mock",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Ingest mock job data",
    description="Load and ingest mock job metadata from JSON file. Creates teams and upserts jobs. "
                "DEV ONLY - Requires ENV=dev."
)
def ingest_mock_job_data(
    *,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key),
) -> Any:
    """
    Ingest mock job metadata into the database.
    
    Security: Only available in dev environment.
    
    This endpoint:
    1. Loads mock job data from backend/app/data/mock_jobs.json
    2. Creates teams if they don't exist (by unique name)
    3. Upserts jobs by job_id (idempotent)
    4. Validates timestamps (end_time >= start_time)
    5. Returns statistics on teams/jobs processed
    
    Authentication:
    - Requires X-API-Key header matching ADMIN_API_KEY
    
    Idempotency:
    - Teams are created only if they don't exist
    - Jobs are upserted based on unique job_id
    - Safe to run multiple times
    
    Returns:
        Statistics on teams and jobs processed
        
    Raises:
        400 Bad Request: If JSON is invalid or validation fails
        401 Unauthorized: If API key is missing or invalid
        403 Forbidden: If ENV is not 'dev'
        500 Internal Server Error: If database operation fails
    """
    # Security: Only allow in dev environment
    if settings.ENV != "dev":
        logger.warning(
            f"Mock job ingestion attempted in non-dev environment: {settings.ENV}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Mock ingestion is only available in dev environment. Current: {settings.ENV}",
        )
    
    try:
        logger.info("Starting mock job data ingestion")
        
        # Run async ingestion service in sync context
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as AsyncSessionClass
        from sqlalchemy.orm import sessionmaker
        from app.core.config import get_settings
        
        settings = get_settings()
        
        # Convert DATABASE_URL to async format
        async_db_url = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        
        async def run_ingestion():
            # Create async engine and session
            engine = create_async_engine(async_db_url, echo=False)
            async_session_maker = sessionmaker(
                engine, class_=AsyncSessionClass, expire_on_commit=False
            )
            
            async with async_session_maker() as session:
                ingestion_service = JobIngestionService(session)
                return await ingestion_service.ingest_jobs()
        
        # Run the async function
        result = asyncio.run(run_ingestion())
        
        if result["jobs"]["failed"] > 0:
            logger.warning(
                f"Job ingestion completed with errors: {result['jobs']['failed']} failed"
            )
            return {
                "status": "partial_success",
                "message": (
                    f"Teams: {result['teams']['created']} created, {result['teams']['existing']} existing. "
                    f"Jobs: {result['jobs']['inserted']} inserted, {result['jobs']['updated']} updated, "
                    f"{result['jobs']['failed']} failed."
                ),
                "result": result
            }
        else:
            logger.info(
                f"Job ingestion successful: "
                f"Teams: {result['teams']['created']} created, {result['teams']['existing']} existing. "
                f"Jobs: {result['jobs']['inserted']} inserted, {result['jobs']['updated']} updated."
            )
            return {
                "status": "success",
                "message": (
                    f"Successfully ingested {result['teams']['total']} teams and "
                    f"{result['jobs']['inserted'] + result['jobs']['updated']} jobs."
                ),
                "result": result
            }
    
    except FileNotFoundError as e:
        logger.error(f"Job data file not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job data file not found: {str(e)}",
        )
    
    except ValueError as e:
        logger.error(f"Job data validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job data: {str(e)}",
        )
    
    except Exception as e:
        logger.error(f"Critical error during job ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest job data. Check server logs for details.",
        )


@router.post(
    "/import/cost/csv",
    response_model=IngestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Import GPU cost data from CSV",
    description="Upload and import GPU cost data from CSV file. "
                "Validates data and performs idempotent upserts. "
                "ADMIN ONLY - Requires X-API-Key header.",
)
def import_cost_csv(
    *,
    file: UploadFile = File(..., description="CSV file with cost data"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_admin_api_key),
) -> Any:
    """
    Import GPU cost data from CSV file.
    
    **CSV Format:**
    - Header row (required): `date,provider,gpu_type,cost_usd`
    - Data rows: `YYYY-MM-DD,<provider>,<gpu_type>,<decimal>`
    
    **Example CSV:**
    ```csv
    date,provider,gpu_type,cost_usd
    2024-01-01,AWS,A100,1245.67
    2024-01-01,AWS,H100,2189.45
    2024-01-02,GCP,A100,1150.00
    ```
    
    **Validation:**
    - Date format: YYYY-MM-DD
    - Provider: Non-empty string (will be lowercased)
    - GPU type: Non-empty string (will be lowercased)
    - Cost: Positive decimal number (will be rounded to 2 decimal places)
    
    **Idempotency:**
    - Records are upserted based on unique key (date, provider, gpu_type)
    - If record exists, only cost_usd is updated
    - Safe to upload the same file multiple times
    
    **Authentication:**
    - Requires X-API-Key header matching ADMIN_API_KEY environment variable
    
    **Returns:**
        IngestionResponse with operation statistics (total_records, inserted, updated, failed, errors)
        
    **Raises:**
        400 Bad Request: If CSV format is invalid, file is empty, or validation fails
        401 Unauthorized: If API key is missing or invalid
        413 Payload Too Large: If file exceeds size limit (configurable, default ~10MB)
        500 Internal Server Error: If database operation fails
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided. Please upload a CSV file.",
        )
    
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.filename}. Only CSV files are supported.",
        )
    
    # Read file content (with size limit for safety)
    max_file_size = 10 * 1024 * 1024  # 10MB limit
    try:
        content = file.file.read(max_file_size + 1)
        if len(content) > max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds limit of {max_file_size / 1024 / 1024:.0f}MB. "
                       f"Please split large files into smaller chunks.",
            )
        
        # Decode CSV content
        csv_content = content.decode("utf-8")
        
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File encoding error. CSV file must be UTF-8 encoded.",
        )
    except Exception as e:
        logger.error(f"Error reading uploaded file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error reading uploaded file. Please try again.",
        )
    
    if not csv_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty. Please upload a file with data.",
        )
    
    try:
        logger.info(f"Starting CSV import from file: {file.filename}")
        
        # Initialize ingestion service
        ingestion_service = CostIngestionService(db)
        
        # Import CSV data
        result = ingestion_service.ingest_cost_data_from_csv(csv_content)
        
        # Build response message
        if result.failed == 0:
            message = (
                f"Successfully imported {result.total_records} records: "
                f"{result.inserted} inserted, {result.updated} updated"
            )
            status_code = "success"
        else:
            message = (
                f"Import completed with {result.failed} error(s): "
                f"{result.inserted} inserted, {result.updated} updated, {result.failed} failed"
            )
            status_code = "partial_success"
        
        logger.info(
            f"CSV import complete: {message} (file: {file.filename})"
        )
        
        return IngestionResponse(
            status=status_code,
            message=message,
            result=result,
        )
        
    except ValueError as e:
        # CSV validation errors - return clear error message
        logger.warning(f"CSV validation error: {e} (file: {file.filename})")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV validation failed: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error during CSV import: {e} (file: {file.filename})", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error importing CSV: {str(e)}",
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Admin health check",
    description="Verify admin API is accessible and API key authentication is working.",
)
def admin_health_check(
    api_key: str = Depends(verify_admin_api_key),
) -> dict:
    """
    Admin health check endpoint.
    
    Verifies that:
    - Admin API is accessible
    - API key authentication is working
    
    Returns:
        Health status
    """
    return {
        "status": "ok",
        "message": "Admin API is healthy and authenticated",
    }

