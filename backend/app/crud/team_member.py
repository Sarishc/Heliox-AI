"""CRUD operations for TeamMember model."""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.crud.tenant_mixin import TenantScopedMixin
from app.models.team_member import TeamMember
from app.schemas.team_member import TeamMemberCreate, TeamMemberUpdate


class CRUDTeamMember(TenantScopedMixin, CRUDBase[TeamMember, TeamMemberCreate, TeamMemberUpdate]):
    def get_by_team_and_user(self, db: Session, *, team_id: UUID, user_id: UUID) -> Optional[TeamMember]:
        return db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id).first()


team_member = CRUDTeamMember(TeamMember)
