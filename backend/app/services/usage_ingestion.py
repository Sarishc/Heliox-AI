"""Usage ingestion service for GPU usage metrics."""

import logging
from decimal import Decimal
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cost import UsageSnapshot
from app.schemas.ingest import UsageMetric

logger = logging.getLogger(__name__)


class UsageIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def ingest_usage_metrics(self, *, team_id: UUID, metrics: List[UsageMetric]) -> dict:
        inserted = 0
        updated = 0
        for metric in metrics:
            usage_date = metric.timestamp.date()
            tags = metric.tags or {}
            env_value = tags.get("environment") or tags.get("env") or "unknown"
            project_value = tags.get("project") or "unknown"
            normalized = {
                "team_id": team_id,
                "date": usage_date,
                "provider": metric.provider.lower().strip(),
                "gpu_type": metric.gpu_type.lower().strip(),
                "environment": str(env_value).lower().strip(),
                "project": str(project_value).lower().strip(),
                "gpu_hours": Decimal(metric.gpu_hours),
            }
            stmt = insert(UsageSnapshot).values(**normalized)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    "team_id",
                    "date",
                    "provider",
                    "gpu_type",
                    "environment",
                    "project",
                ],
                set_={
                    "gpu_hours": UsageSnapshot.gpu_hours + stmt.excluded.gpu_hours,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            existing = self.db.execute(
                select(UsageSnapshot).where(
                    UsageSnapshot.team_id == team_id,
                    UsageSnapshot.date == usage_date,
                    UsageSnapshot.provider == normalized["provider"],
                    UsageSnapshot.gpu_type == normalized["gpu_type"],
                    UsageSnapshot.environment == normalized["environment"],
                    UsageSnapshot.project == normalized["project"],
                )
            ).first()
            try:
                self.db.execute(stmt)
            except OperationalError:
                # SQLite fallback (no ON CONFLICT with PG insert)
                if existing:
                    snapshot = existing[0]
                    snapshot.gpu_hours = snapshot.gpu_hours + normalized["gpu_hours"]
                else:
                    self.db.add(UsageSnapshot(**normalized))
            if existing:
                updated += 1
            else:
                inserted += 1
        self.db.commit()
        return {"inserted": inserted, "updated": updated, "total": len(metrics)}
