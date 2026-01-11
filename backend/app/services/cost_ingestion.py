"""Cost ingestion service for processing and storing cost data."""
import csv
import io
import json
import logging
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot

logger = logging.getLogger(__name__)


class CostDataRecord(BaseModel):
    """Schema for validating individual cost data records."""
    
    date: date_type = Field(..., description="Date of the cost snapshot")
    provider: str = Field(..., min_length=1, max_length=100, description="Cloud provider")
    gpu_type: str = Field(..., min_length=1, max_length=100, description="GPU type")
    cost_usd: Decimal = Field(..., gt=0, description="Cost in USD")
    
    @field_validator("cost_usd")
    @classmethod
    def validate_cost(cls, v: Decimal) -> Decimal:
        """Validate and round cost to 2 decimal places."""
        if v <= 0:
            raise ValueError("Cost must be positive")
        return round(v, 2)


class CostExport(BaseModel):
    """Schema for validating the entire cost export file."""
    
    export_metadata: Optional[Dict] = Field(None, description="Export metadata")
    cost_data: List[CostDataRecord] = Field(..., min_length=1, description="List of cost records")


class IngestionResult(BaseModel):
    """Result of cost ingestion operation."""
    
    total_records: int
    inserted: int
    updated: int
    failed: int
    errors: List[str] = Field(default_factory=list)


class CostIngestionService:
    """
    Service for ingesting cost data into the database.
    
    Handles:
    - Loading and validating cost data from JSON
    - Normalizing provider and GPU type strings
    - Idempotent upsert operations (based on date, provider, gpu_type)
    - Error handling and logging
    """
    
    def __init__(self, db: Session):
        """
        Initialize the cost ingestion service.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
    
    @staticmethod
    def load_mock_data(file_path: Optional[Path] = None) -> CostExport:
        """
        Load and validate mock cost data from JSON file.
        
        Args:
            file_path: Path to JSON file. If None, uses default mock data location.
            
        Returns:
            Validated CostExport object
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
            ValidationError: If the data doesn't match the expected schema
        """
        if file_path is None:
            # Default to mock data file in app/data/
            file_path = Path(__file__).parent.parent / "data" / "mock_cost_export.json"
        
        logger.info(f"Loading cost data from: {file_path}")
        
        if not file_path.exists():
            raise FileNotFoundError(f"Cost data file not found: {file_path}")
        
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in cost data file: {e}")
            raise
        
        try:
            cost_export = CostExport(**data)
            logger.info(f"Successfully loaded {len(cost_export.cost_data)} cost records")
            return cost_export
        except ValidationError as e:
            logger.error(f"Cost data validation failed: {e}")
            raise
    
    @staticmethod
    def normalize_record(record: CostDataRecord) -> Dict:
        """
        Normalize a cost data record.
        
        Normalization includes:
        - Lowercasing provider and gpu_type for consistency
        - Ensuring cost is rounded to 2 decimal places
        
        Args:
            record: Cost data record to normalize
            
        Returns:
            Dictionary with normalized data
        """
        return {
            "date": record.date,
            "provider": record.provider.lower().strip(),
            "gpu_type": record.gpu_type.lower().strip(),
            "cost_usd": round(record.cost_usd, 2),
        }
    
    def upsert_cost_snapshot(self, normalized_data: Dict) -> str:
        """
        Upsert a cost snapshot record.
        
        Uses PostgreSQL's ON CONFLICT DO UPDATE for idempotent inserts.
        If a record with the same (date, provider, gpu_type) exists, updates the cost.
        
        Args:
            normalized_data: Normalized cost data dictionary
            
        Returns:
            "inserted" or "updated" to indicate the operation performed
            
        Raises:
            Exception: If database operation fails
        """
        # PostgreSQL upsert statement
        stmt = insert(CostSnapshot).values(**normalized_data)
        
        # Define what to do on conflict (when record already exists)
        # Update the cost_usd and updated_at timestamp
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "provider", "gpu_type"],
            set_={
                "cost_usd": stmt.excluded.cost_usd,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        
        # Check if record existed before upsert to determine if insert or update
        existing = self.db.execute(
            select(CostSnapshot).where(
                CostSnapshot.date == normalized_data["date"],
                CostSnapshot.provider == normalized_data["provider"],
                CostSnapshot.gpu_type == normalized_data["gpu_type"],
            )
        ).first()
        
        # Execute the upsert
        self.db.execute(stmt)
        
        return "updated" if existing else "inserted"
    
    @staticmethod
    def parse_csv_file(csv_content: str) -> List[CostDataRecord]:
        """
        Parse CSV content and return list of validated CostDataRecord objects.
        
        Expected CSV format:
        - Header row: date,provider,gpu_type,cost_usd
        - Data rows: YYYY-MM-DD,<provider>,<gpu_type>,<decimal>
        
        Args:
            csv_content: CSV file content as string
            
        Returns:
            List of validated CostDataRecord objects
            
        Raises:
            ValueError: If CSV format is invalid or data validation fails
        """
        errors: List[str] = []
        records: List[CostDataRecord] = []
        
        try:
            # Parse CSV
            reader = csv.DictReader(io.StringIO(csv_content))
            
            # Validate header
            expected_headers = {"date", "provider", "gpu_type", "cost_usd"}
            if not reader.fieldnames:
                raise ValueError("CSV file is empty or has no header row")
            
            actual_headers = set(reader.fieldnames)
            if not expected_headers.issubset(actual_headers):
                missing = expected_headers - actual_headers
                raise ValueError(
                    f"CSV header is missing required columns: {', '.join(missing)}. "
                    f"Expected columns: {', '.join(sorted(expected_headers))}"
                )
            
            # Parse and validate each row
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    # Extract and validate date
                    date_str = row.get("date", "").strip()
                    if not date_str:
                        errors.append(f"Row {row_num}: Missing date field")
                        continue
                    
                    try:
                        date_value = date_type.fromisoformat(date_str)
                    except ValueError:
                        errors.append(
                            f"Row {row_num}: Invalid date format '{date_str}'. Expected YYYY-MM-DD"
                        )
                        continue
                    
                    # Extract and validate provider
                    provider = row.get("provider", "").strip()
                    if not provider:
                        errors.append(f"Row {row_num}: Missing provider field")
                        continue
                    
                    # Extract and validate gpu_type
                    gpu_type = row.get("gpu_type", "").strip()
                    if not gpu_type:
                        errors.append(f"Row {row_num}: Missing gpu_type field")
                        continue
                    
                    # Extract and validate cost_usd
                    cost_str = row.get("cost_usd", "").strip()
                    if not cost_str:
                        errors.append(f"Row {row_num}: Missing cost_usd field")
                        continue
                    
                    try:
                        cost_value = Decimal(cost_str)
                        if cost_value <= 0:
                            errors.append(
                                f"Row {row_num}: cost_usd must be positive, got {cost_str}"
                            )
                            continue
                    except (InvalidOperation, ValueError):
                        errors.append(
                            f"Row {row_num}: Invalid cost_usd value '{cost_str}'. Expected decimal number"
                        )
                        continue
                    
                    # Create and validate record using Pydantic
                    record = CostDataRecord(
                        date=date_value,
                        provider=provider,
                        gpu_type=gpu_type,
                        cost_usd=cost_value,
                    )
                    records.append(record)
                    
                except ValidationError as e:
                    # Pydantic validation errors
                    error_messages = "; ".join(
                        f"{err['loc'][0]}: {err['msg']}" for err in e.errors()
                    )
                    errors.append(f"Row {row_num}: {error_messages}")
                    continue
                except Exception as e:
                    errors.append(f"Row {row_num}: Unexpected error: {str(e)}")
                    continue
            
            if errors and not records:
                # If we have errors and no valid records, raise with all errors
                raise ValueError(
                    f"CSV parsing failed with {len(errors)} error(s). "
                    f"First error: {errors[0]}"
                )
            
            if not records:
                raise ValueError("CSV file contains no valid data rows")
            
            logger.info(
                f"Successfully parsed {len(records)} records from CSV"
                + (f" ({len(errors)} rows had errors)" if errors else "")
            )
            
            return records
            
        except csv.Error as e:
            raise ValueError(f"CSV parsing error: {str(e)}")
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Error parsing CSV file: {str(e)}")
    
    def ingest_cost_data(
        self,
        file_path: Optional[Path] = None
    ) -> IngestionResult:
        """
        Ingest cost data from file into database.
        
        Process:
        1. Load and validate JSON data
        2. Normalize each record
        3. Upsert into database with idempotency
        4. Track inserted/updated/failed counts
        5. Commit transaction if successful
        
        Args:
            file_path: Path to JSON file. If None, uses default mock data.
            
        Returns:
            IngestionResult with operation statistics
            
        Raises:
            Exception: If critical error occurs during ingestion
        """
        result = IngestionResult(
            total_records=0,
            inserted=0,
            updated=0,
            failed=0,
        )
        
        try:
            # Load and validate data
            cost_export = self.load_mock_data(file_path)
            result.total_records = len(cost_export.cost_data)
            
            logger.info(f"Starting ingestion of {result.total_records} cost records")
            
            # Process each record
            for idx, record in enumerate(cost_export.cost_data, 1):
                try:
                    # Normalize data
                    normalized_data = self.normalize_record(record)
                    
                    # Upsert to database
                    operation = self.upsert_cost_snapshot(normalized_data)
                    
                    if operation == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1
                    
                    logger.debug(
                        f"Record {idx}/{result.total_records}: {operation} "
                        f"{normalized_data['date']} | {normalized_data['provider']} | "
                        f"{normalized_data['gpu_type']} | ${normalized_data['cost_usd']}"
                    )
                
                except Exception as e:
                    result.failed += 1
                    error_msg = f"Record {idx}: {str(e)}"
                    result.errors.append(error_msg)
                    logger.error(f"Failed to process record {idx}: {e}")
                    continue
            
            # Commit all changes if we got here without critical errors
            self.db.commit()
            
            logger.info(
                f"Ingestion complete: {result.inserted} inserted, "
                f"{result.updated} updated, {result.failed} failed"
            )
            
            return result
        
        except Exception as e:
            # Rollback on critical errors
            self.db.rollback()
            logger.error(f"Critical error during ingestion: {e}")
            raise
    
    def ingest_cost_data_from_csv(self, csv_content: str) -> IngestionResult:
        """
        Ingest cost data from CSV content into database.
        
        Process:
        1. Parse and validate CSV content
        2. Normalize each record
        3. Upsert into database with idempotency
        4. Track inserted/updated/failed counts
        5. Commit transaction if successful
        
        Args:
            csv_content: CSV file content as string
            
        Returns:
            IngestionResult with operation statistics
            
        Raises:
            ValueError: If CSV format is invalid or data validation fails
            Exception: If critical error occurs during ingestion
        """
        result = IngestionResult(
            total_records=0,
            inserted=0,
            updated=0,
            failed=0,
        )
        
        try:
            # Parse and validate CSV
            records = self.parse_csv_file(csv_content)
            result.total_records = len(records)
            
            logger.info(f"Starting CSV ingestion of {result.total_records} cost records")
            
            # Process each record
            for idx, record in enumerate(records, 1):
                try:
                    # Normalize data
                    normalized_data = self.normalize_record(record)
                    
                    # Upsert to database
                    operation = self.upsert_cost_snapshot(normalized_data)
                    
                    if operation == "inserted":
                        result.inserted += 1
                    else:
                        result.updated += 1
                    
                    logger.debug(
                        f"Record {idx}/{result.total_records}: {operation} "
                        f"{normalized_data['date']} | {normalized_data['provider']} | "
                        f"{normalized_data['gpu_type']} | ${normalized_data['cost_usd']}"
                    )
                
                except Exception as e:
                    result.failed += 1
                    error_msg = f"Record {idx}: {str(e)}"
                    result.errors.append(error_msg)
                    logger.error(f"Failed to process record {idx}: {e}")
                    continue
            
            # Commit all changes if we got here without critical errors
            self.db.commit()
            
            logger.info(
                f"CSV ingestion complete: {result.inserted} inserted, "
                f"{result.updated} updated, {result.failed} failed"
            )
            
            return result
        
        except ValueError as e:
            # CSV parsing/validation errors - don't commit
            self.db.rollback()
            logger.error(f"CSV validation error: {e}")
            # Re-raise as ValueError with clear message
            raise
        except Exception as e:
            # Rollback on critical errors
            self.db.rollback()
            logger.error(f"Critical error during CSV ingestion: {e}")
            raise

