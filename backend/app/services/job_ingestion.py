"""
Job ingestion service for loading mock job data and creating jobs/teams.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

import logging

logger = logging.getLogger(__name__)
from app.models.job import Job
from app.models.team import Team


class TeamData(BaseModel):
    """Schema for team data in mock JSON."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    budget_usd: float = Field(gt=0, description="Team budget in USD")


class JobData(BaseModel):
    """Schema for job data in mock JSON."""
    job_id: str = Field(..., min_length=1, max_length=100)
    team_name: str = Field(..., min_length=1, max_length=100)
    model_name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(..., min_length=1, max_length=100)
    gpu_type: str = Field(..., min_length=1, max_length=100)
    start_time: datetime
    end_time: datetime | None = None
    status: str = Field(default="pending")
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate job status."""
        valid_statuses = ["pending", "running", "completed", "failed", "cancelled"]
        if v.lower() not in valid_statuses:
            raise ValueError(f"Status must be one of {valid_statuses}")
        return v.lower()
    
    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: datetime | None, info) -> datetime | None:
        """Validate end_time is after start_time."""
        if v is not None:
            start_time = info.data.get("start_time")
            if start_time and v < start_time:
                raise ValueError("end_time must be >= start_time")
        return v


class MockJobsData(BaseModel):
    """Schema for the complete mock jobs JSON file."""
    teams: List[TeamData]
    jobs: List[JobData]


class JobIngestionService:
    """
    Service for ingesting job metadata into the database.
    
    Handles:
    - Loading and validating mock JSON
    - Creating teams if they don't exist
    - Upserting jobs by job_id
    - Data normalization
    """
    
    def __init__(self, db_session: AsyncSession):
        """
        Initialize the job ingestion service.
        
        Args:
            db_session: Async database session
        """
        self.db_session = db_session
        self.mock_data_path = Path(__file__).parent.parent / "data" / "mock_jobs.json"
    
    async def load_mock_data(self) -> MockJobsData:
        """
        Load and validate mock job data from JSON file.
        
        Returns:
            MockJobsData: Validated mock data
            
        Raises:
            FileNotFoundError: If mock data file doesn't exist
            ValueError: If JSON is invalid or validation fails
        """
        if not self.mock_data_path.exists():
            logger.error(f"Mock job data file not found: {self.mock_data_path}")
            raise FileNotFoundError(f"Mock job data file not found: {self.mock_data_path}")
        
        try:
            with open(self.mock_data_path, "r") as f:
                data = json.load(f)
            logger.info(f"Successfully loaded mock job data from {self.mock_data_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in mock job data file: {e}")
            raise ValueError(f"Invalid JSON format in mock job data: {e}")
        
        try:
            mock_data = MockJobsData(**data)
            logger.info(
                f"Validated mock data: {len(mock_data.teams)} teams, "
                f"{len(mock_data.jobs)} jobs"
            )
            return mock_data
        except ValidationError as e:
            logger.error(f"Mock job data validation failed: {e}")
            raise ValueError(f"Mock job data validation failed: {e}")
    
    async def get_or_create_team(self, team_data: TeamData) -> Team:
        """
        Get existing team by name or create a new one.
        
        Args:
            team_data: Team data to create if not exists
            
        Returns:
            Team: Existing or newly created team
        """
        # Check if team exists
        result = await self.db_session.execute(
            select(Team).where(Team.name == team_data.name)
        )
        team = result.scalar_one_or_none()
        
        if team:
            logger.debug(f"Team '{team_data.name}' already exists (ID: {team.id})")
            return team
        
        # Create new team (only use fields that exist in Team model)
        team = Team(
            name=team_data.name
        )
        self.db_session.add(team)
        await self.db_session.flush()  # Get the ID without committing
        
        logger.info(f"Created new team '{team_data.name}' (ID: {team.id})")
        return team
    
    async def upsert_job(self, job_data: JobData, team_id: UUID) -> tuple[str, bool]:
        """
        Insert or update a job by job_id.
        
        Uses PostgreSQL's ON CONFLICT DO UPDATE for idempotency.
        
        Args:
            job_data: Job data to insert/update
            team_id: UUID of the team this job belongs to
            
        Returns:
            tuple[str, bool]: (job_id, was_inserted)
        """
        # Normalize data
        normalized_data = {
            "job_id": job_data.job_id,
            "team_id": team_id,
            "model_name": job_data.model_name.lower(),
            "provider": job_data.provider.lower(),
            "gpu_type": job_data.gpu_type.lower(),
            "start_time": job_data.start_time,
            "end_time": job_data.end_time,
            "status": job_data.status.lower()
        }
        
        # Perform upsert
        stmt = insert(Job).values(**normalized_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_id"],
            set_={
                "team_id": stmt.excluded.team_id,
                "model_name": stmt.excluded.model_name,
                "provider": stmt.excluded.provider,
                "gpu_type": stmt.excluded.gpu_type,
                "start_time": stmt.excluded.start_time,
                "end_time": stmt.excluded.end_time,
                "status": stmt.excluded.status,
                "updated_at": stmt.excluded.updated_at,
            }
        )
        
        result = await self.db_session.execute(stmt)
        
        # Determine if it was an insert or update
        # If rowcount is 1 and we have returning data, it was likely an insert
        # This is a simplified check; in production you might track this differently
        was_inserted = result.rowcount > 0
        
        return job_data.job_id, was_inserted
    
    async def ingest_jobs(self) -> Dict[str, Any]:
        """
        Ingest all jobs and teams from mock data.
        
        Process:
        1. Load and validate mock JSON
        2. Create/get teams
        3. Upsert jobs
        
        Returns:
            Dict with ingestion statistics
        """
        logger.info("Starting job ingestion from mock data")
        
        # Load mock data
        mock_data = await self.load_mock_data()
        
        # Track team name to ID mapping
        team_map: Dict[str, UUID] = {}
        
        # Create/get all teams first
        teams_created = 0
        teams_existing = 0
        
        for team_data in mock_data.teams:
            try:
                # Check if team exists before creating
                result = await self.db_session.execute(
                    select(Team).where(Team.name == team_data.name)
                )
                existing_team = result.scalar_one_or_none()
                
                if existing_team:
                    team = existing_team
                    teams_existing += 1
                else:
                    team = await self.get_or_create_team(team_data)
                    teams_created += 1
                
                team_map[team_data.name] = team.id
                
            except Exception as e:
                logger.error(f"Failed to process team '{team_data.name}': {e}")
                await self.db_session.rollback()
                raise
        
        await self.db_session.commit()
        logger.info(
            f"Teams processed: {teams_created} created, {teams_existing} existing"
        )
        
        # Ingest jobs
        jobs_inserted = 0
        jobs_updated = 0
        jobs_failed = 0
        errors = []
        
        for job_data in mock_data.jobs:
            try:
                team_id = team_map.get(job_data.team_name)
                if not team_id:
                    raise ValueError(f"Team '{job_data.team_name}' not found in team map")
                
                # Check if job exists before upserting
                result = await self.db_session.execute(
                    select(Job).where(Job.job_id == job_data.job_id)
                )
                existing_job = result.scalar_one_or_none()
                
                job_id, was_inserted = await self.upsert_job(job_data, team_id)
                
                if existing_job is None:
                    jobs_inserted += 1
                    logger.debug(f"Inserted job '{job_id}'")
                else:
                    jobs_updated += 1
                    logger.debug(f"Updated job '{job_id}'")
                
                await self.db_session.commit()
                
            except Exception as e:
                await self.db_session.rollback()
                logger.error(f"Failed to ingest job '{job_data.job_id}': {e}")
                jobs_failed += 1
                errors.append(f"Job {job_data.job_id}: {str(e)}")
        
        result = {
            "teams": {
                "created": teams_created,
                "existing": teams_existing,
                "total": teams_created + teams_existing
            },
            "jobs": {
                "inserted": jobs_inserted,
                "updated": jobs_updated,
                "failed": jobs_failed,
                "total": len(mock_data.jobs)
            },
            "errors": errors
        }
        
        logger.info(
            f"Job ingestion complete: "
            f"Teams ({teams_created} created, {teams_existing} existing), "
            f"Jobs ({jobs_inserted} inserted, {jobs_updated} updated, {jobs_failed} failed)"
        )
        
        return result

