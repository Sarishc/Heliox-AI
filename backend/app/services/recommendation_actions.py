"""Recommendation action service - apply/dismiss tracking with fingerprint deduplication."""
import hashlib
import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.recommendation_action import RecommendationAction
from app.schemas.recommendation import Recommendation

logger = logging.getLogger(__name__)


def _evidence_dict(evidence: Any) -> dict:
    """Normalize evidence to dict."""
    if evidence is None:
        return {}
    if isinstance(evidence, dict):
        return evidence
    if hasattr(evidence, "model_dump"):
        return evidence.model_dump()
    if hasattr(evidence, "dict"):
        return evidence.dict()
    return {}


def recommendation_fingerprint(rec: Recommendation) -> str:
    """
    Create deterministic fingerprint for recommendation deduplication.

    Same logical recommendation (type + key evidence) yields same fingerprint
    across refreshes, enabling status display and idempotent apply/dismiss.
    """
    evidence = _evidence_dict(rec.evidence)
    date_range = evidence.get("date_range") or {}
    payload = {
        "type": rec.type.value if hasattr(rec.type, "value") else str(rec.type),
        "provider": evidence.get("provider"),
        "gpu_type": evidence.get("gpu_type"),
        "job_id": evidence.get("job_id"),
        "team_name": evidence.get("team_name"),
        "start_date": date_range.get("start_date") if isinstance(date_range, dict) else None,
        "end_date": date_range.get("end_date") if isinstance(date_range, dict) else None,
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def get_action_status(
    db: Session,
    team_id: UUID,
    fingerprints: list[str],
) -> dict[str, str]:
    """Return status by fingerprint for given team."""
    if not fingerprints:
        return {}
    rows = (
        db.query(RecommendationAction.recommendation_fingerprint, RecommendationAction.status)
        .filter(
            RecommendationAction.team_id == team_id,
            RecommendationAction.recommendation_fingerprint.in_(fingerprints),
        )
        .all()
    )
    return {r.recommendation_fingerprint: r.status for r in rows}


def apply_recommendation(
    db: Session,
    team_id: UUID,
    recommendation: Recommendation | dict,
    status: str,  # "applied" | "dismissed"
    user_id: Optional[UUID] = None,
) -> tuple[RecommendationAction | None, bool]:
    """
    Record apply or dismiss action. Idempotent: same fingerprint updates status.

    Returns:
        (RecommendationAction, created) - created=True if new row, False if updated
    """
    if isinstance(recommendation, dict):
        rec = Recommendation.model_validate(recommendation)
    else:
        rec = recommendation
    fp = recommendation_fingerprint(rec)
    existing = (
        db.query(RecommendationAction)
        .filter(
            RecommendationAction.team_id == team_id,
            RecommendationAction.recommendation_fingerprint == fp,
        )
        .first()
    )
    evidence = _evidence_dict(rec.evidence)
    provider = evidence.get("provider")
    gpu_type = evidence.get("gpu_type")
    snapshot = {
        "title": rec.title,
        "description": rec.description[:500] if rec.description else "",
        "type": rec.type.value if hasattr(rec.type, "value") else str(rec.type),
        "estimated_savings_usd": rec.estimated_savings_usd,
    }
    if existing:
        existing.status = status
        existing.estimated_savings_usd = rec.estimated_savings_usd
        existing.recommendation_snapshot = snapshot
        existing.applied_by_user_id = user_id
        db.commit()
        db.refresh(existing)
        return existing, False
    action = RecommendationAction(
        team_id=team_id,
        recommendation_fingerprint=fp,
        status=status,
        action_type=rec.type.value if hasattr(rec.type, "value") else str(rec.type),
        estimated_savings_usd=rec.estimated_savings_usd,
        recommendation_snapshot=snapshot,
        applied_by_user_id=user_id,
        provider=provider,
        gpu_type=gpu_type,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action, True


def list_actions(
    db: Session,
    team_id: UUID,
    status_filter: Optional[str] = None,
    limit: int = 100,
) -> list[RecommendationAction]:
    """List recommendation actions for a team."""
    q = db.query(RecommendationAction).filter(RecommendationAction.team_id == team_id)
    if status_filter:
        q = q.filter(RecommendationAction.status == status_filter)
    return q.order_by(RecommendationAction.created_at.desc()).limit(limit).all()
