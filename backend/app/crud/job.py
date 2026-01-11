"""CRUD operations for Job model."""
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.job import Job
from app.schemas.job import JobCreate, JobUpdate


class CRUDJob(CRUDBase[Job, JobCreate, JobUpdate]):
    """CRUD operations for Job model."""
    
    def get_by_team(
        self,
        db: Session,
        *,
        team_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """
        Get jobs by team ID.
        
        Args:
            db: Database session
            team_id: Team UUID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Job instances
        """
        return (
            db.query(Job)
            .filter(Job.team_id == team_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_status(
        self,
        db: Session,
        *,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """
        Get jobs by status.
        
        Args:
            db: Database session
            status: Job status
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Job instances
        """
        return (
            db.query(Job)
            .filter(Job.status == status)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_provider(
        self,
        db: Session,
        *,
        provider: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """
        Get jobs by provider.
        
        Args:
            db: Database session
            provider: Cloud provider name
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Job instances
        """
        return (
            db.query(Job)
            .filter(Job.provider == provider)
            .offset(skip)
            .limit(limit)
            .all()
        )


job = CRUDJob(Job)

