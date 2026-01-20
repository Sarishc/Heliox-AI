"""CRUD operations for Cost and Usage snapshot models."""
from datetime import date
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.crud.base import CRUDBase
from app.models.cost import CostSnapshot, UsageSnapshot
from app.schemas.cost import CostSnapshotCreate, UsageSnapshotCreate


class CRUDCostSnapshot(CRUDBase[CostSnapshot, CostSnapshotCreate, None]):
    """CRUD operations for CostSnapshot model."""
    
    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        team_id
    ) -> List[CostSnapshot]:
        return (
            db.query(CostSnapshot)
            .filter(CostSnapshot.team_id == team_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_date_range(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        team_id
    ) -> List[CostSnapshot]:
        """
        Get cost snapshots by date range.
        
        Args:
            db: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of CostSnapshot instances
        """
        return (
            db.query(CostSnapshot)
            .filter(
                and_(
                    CostSnapshot.team_id == team_id,
                    CostSnapshot.date >= start_date,
                    CostSnapshot.date <= end_date
                )
            )
            .order_by(CostSnapshot.date.desc())
            .all()
        )
    
    def get_by_provider(
        self,
        db: Session,
        *,
        provider: str,
        start_date: date,
        end_date: date,
        team_id
    ) -> List[CostSnapshot]:
        """
        Get cost snapshots by provider and date range.
        
        Args:
            db: Database session
            provider: Cloud provider name
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of CostSnapshot instances
        """
        return (
            db.query(CostSnapshot)
            .filter(
                and_(
                    CostSnapshot.team_id == team_id,
                    CostSnapshot.provider == provider,
                    CostSnapshot.date >= start_date,
                    CostSnapshot.date <= end_date
                )
            )
            .order_by(CostSnapshot.date.desc())
            .all()
        )
    
    def get_total_cost(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        team_id
    ) -> float:
        """
        Get total cost for date range.
        
        Args:
            db: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            Total cost as float
        """
        result = db.query(
            func.sum(CostSnapshot.cost_usd)
        ).filter(
            and_(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start_date,
                CostSnapshot.date <= end_date
            )
        ).scalar()
        return float(result) if result else 0.0


class CRUDUsageSnapshot(CRUDBase[UsageSnapshot, UsageSnapshotCreate, None]):
    """CRUD operations for UsageSnapshot model."""
    
    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        team_id
    ) -> List[UsageSnapshot]:
        return (
            db.query(UsageSnapshot)
            .filter(UsageSnapshot.team_id == team_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_by_date_range(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        team_id
    ) -> List[UsageSnapshot]:
        """
        Get usage snapshots by date range.
        
        Args:
            db: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of UsageSnapshot instances
        """
        return (
            db.query(UsageSnapshot)
            .filter(
                and_(
                    UsageSnapshot.team_id == team_id,
                    UsageSnapshot.date >= start_date,
                    UsageSnapshot.date <= end_date
                )
            )
            .order_by(UsageSnapshot.date.desc())
            .all()
        )
    
    def get_by_provider(
        self,
        db: Session,
        *,
        provider: str,
        start_date: date,
        end_date: date,
        team_id
    ) -> List[UsageSnapshot]:
        """
        Get usage snapshots by provider and date range.
        
        Args:
            db: Database session
            provider: Cloud provider name
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of UsageSnapshot instances
        """
        return (
            db.query(UsageSnapshot)
            .filter(
                and_(
                    UsageSnapshot.team_id == team_id,
                    UsageSnapshot.provider == provider,
                    UsageSnapshot.date >= start_date,
                    UsageSnapshot.date <= end_date
                )
            )
            .order_by(UsageSnapshot.date.desc())
            .all()
        )
    
    def get_total_hours(
        self,
        db: Session,
        *,
        start_date: date,
        end_date: date,
        team_id
    ) -> float:
        """
        Get total GPU hours for date range.
        
        Args:
            db: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            Total hours as float
        """
        result = db.query(
            func.sum(UsageSnapshot.gpu_hours)
        ).filter(
            and_(
                UsageSnapshot.team_id == team_id,
                UsageSnapshot.date >= start_date,
                UsageSnapshot.date <= end_date
            )
        ).scalar()
        return float(result) if result else 0.0


cost_snapshot = CRUDCostSnapshot(CostSnapshot)
usage_snapshot = CRUDUsageSnapshot(UsageSnapshot)

