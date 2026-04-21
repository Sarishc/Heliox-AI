"""
Tenant-scoped CRUD mixin for multi-tenant isolation.

NEVER load cross-tenant data into memory. All get/delete operations
must filter by team_id at the database level.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.base import Base


class TenantScopedMixin:
    """
    Mixin for CRUD classes on models with team_id.
    Provides get_by_team and delete_by_team that filter at DB level.
    """

    def get_by_team(
        self,
        db: Session,
        *,
        id: UUID,
        team_id: UUID,
    ) -> Optional[Base]:
        """
        Get a single record by ID scoped to team.
        Returns None if not found or team mismatch (404 without leaking existence).
        """
        return db.query(self.model).filter(self.model.id == id, self.model.team_id == team_id).first()

    def delete_by_team(
        self,
        db: Session,
        *,
        id: UUID,
        team_id: UUID,
    ) -> bool:
        """
        Delete a record by ID scoped to team.
        Returns True if deleted, False if not found (no cross-tenant leak).
        """
        obj = db.query(self.model).filter(self.model.id == id, self.model.team_id == team_id).first()
        if obj:
            db.delete(obj)
            db.commit()
            return True
        return False
