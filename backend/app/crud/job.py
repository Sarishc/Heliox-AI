"""CRUD operations for Job model.

Every read is scoped to a set of team IDs in the SQL itself; there are no
unscoped list helpers. Single-job lookup by team comes from TenantScopedMixin.
"""

from typing import List, Optional, Sequence, Tuple
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.crud.tenant_mixin import TenantScopedMixin
from app.models.job import Job
from app.schemas.job import JobCreate, JobUpdate


class DuplicateJobIdError(Exception):
    """The external job_id is already used by another job of the same team (unique per team)."""


class CRUDJob(TenantScopedMixin, CRUDBase[Job, JobCreate, JobUpdate]):
    """CRUD operations for Job model."""

    @staticmethod
    def _scoped(team_ids: Sequence[UUID], *, status: Optional[str] = None, provider: Optional[str] = None) -> Select:
        # Tenant predicate first; optional filters only narrow it further
        stmt = select(Job).where(Job.team_id.in_(list(team_ids)))
        if status:
            stmt = stmt.where(Job.status == status)
        if provider:
            stmt = stmt.where(func.lower(Job.provider) == provider.lower())
        return stmt

    def list_for_teams(
        self,
        db: Session,
        *,
        team_ids: Sequence[UUID],
        status: Optional[str] = None,
        provider: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Job], int]:
        """Jobs in ``team_ids`` matching the filters, and the total count under the same predicate."""
        if not team_ids:
            return [], 0
        stmt = self._scoped(team_ids, status=status, provider=provider)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = db.execute(stmt.order_by(Job.created_at.desc(), Job.id).offset(skip).limit(limit)).scalars().all()
        return list(rows), total

    def get_for_teams(self, db: Session, *, id: UUID, team_ids: Sequence[UUID]) -> Optional[Job]:
        if not team_ids:
            return None
        return db.execute(self._scoped(team_ids).where(Job.id == id)).scalar_one_or_none()

    def create_for_team(self, db: Session, *, obj_in: JobCreate) -> Job:
        """Create a job; generates job_id when the client didn't send one."""
        data = obj_in.model_dump()
        data["job_id"] = data.get("job_id") or f"job_{uuid4().hex}"
        job = Job(**data)
        try:
            # Savepoint so a duplicate job_id doesn't poison the outer transaction
            with db.begin_nested():
                db.add(job)
                db.flush()
        except IntegrityError as exc:
            raise DuplicateJobIdError(data["job_id"]) from exc
        db.commit()
        db.refresh(job)
        return job


job = CRUDJob(Job)
