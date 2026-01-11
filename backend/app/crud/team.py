"""CRUD operations for Team model."""
from typing import Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models.team import Team
from app.schemas.team import TeamCreate, TeamUpdate


class CRUDTeam(CRUDBase[Team, TeamCreate, TeamUpdate]):
    """CRUD operations for Team model."""
    
    def get_by_name(self, db: Session, *, name: str) -> Optional[Team]:
        """
        Get a team by name.
        
        Args:
            db: Database session
            name: Team name
            
        Returns:
            Team instance or None if not found
        """
        return db.query(Team).filter(Team.name == name).first()


team = CRUDTeam(Team)

