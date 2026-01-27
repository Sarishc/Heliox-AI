"""Public share link endpoint."""
import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.reporting import ReportShareLink, SavedReport
from app.schemas.reporting import PublicReportResponse
from app.services.reports import ReportService

router = APIRouter()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.get("/share/{token}", response_model=PublicReportResponse, tags=["Public"])
def get_shared_report(token: str, db: Session = Depends(get_db)) -> PublicReportResponse:
    token_hash = _hash_token(token)
    link = (
        db.query(ReportShareLink)
        .filter(ReportShareLink.token_hash == token_hash)
        .first()
    )
    now = datetime.utcnow()
    if not link or link.revoked_at or link.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    report = db.query(SavedReport).filter(SavedReport.id == link.report_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    service = ReportService(db)
    data = service.build_report_payload(team_id=link.team_id, config=report.config_json)
    return PublicReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        config=data["config"],
        generated_at=data["generated_at"],
        data=data["data"],
    )
