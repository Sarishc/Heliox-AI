"""Saved reports CRUD and export endpoints."""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.models.reporting import ReportRun, ReportShareLink, SavedReport
from app.models.team_api_key import TeamAPIKey
from app.schemas.reporting import (
    ReportFileType,
    ReportRunCreate,
    ReportRunResponse,
    ReportShareCreate,
    ReportShareResponse,
    SavedReportCreate,
    SavedReportResponse,
    SavedReportUpdate,
)
from app.services.reports import ReportService

router = APIRouter()
settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("", response_model=SavedReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: SavedReportCreate,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    report = SavedReport(
        team_id=team_id,
        name=payload.name,
        description=payload.description,
        config_json=payload.config.model_dump(),
        created_by_user_id=None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[SavedReportResponse])
def list_reports(
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    return (
        db.query(SavedReport)
        .filter(SavedReport.team_id == team_id)
        .order_by(SavedReport.created_at.desc())
        .all()
    )


@router.get("/{report_id}", response_model=SavedReportResponse)
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == report_id, SavedReport.team_id == team_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.put("/{report_id}", response_model=SavedReportResponse)
def update_report(
    report_id: UUID,
    payload: SavedReportUpdate,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == report_id, SavedReport.team_id == team_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if payload.name is not None:
        report.name = payload.name
    if payload.description is not None:
        report.description = payload.description
    if payload.config is not None:
        report.config_json = payload.config.model_dump()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> None:
    team_id = get_effective_team_id(team_api_key)
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == report_id, SavedReport.team_id == team_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    db.delete(report)
    db.commit()


@router.post("/{report_id}/run", response_model=ReportRunResponse, status_code=status.HTTP_201_CREATED)
def run_report(
    report_id: UUID,
    payload: ReportRunCreate,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == report_id, SavedReport.team_id == team_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    service = ReportService(db)
    report_run = service.generate_report(
        team_id=team_id,
        report=report,
        file_type=payload.file_type.value,
    )
    return report_run


@router.get("/runs/{run_id}/download")
def download_report(
    run_id: UUID,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> FileResponse:
    team_id = get_effective_team_id(team_api_key)
    report_run = (
        db.query(ReportRun)
        .filter(ReportRun.id == run_id, ReportRun.team_id == team_id)
        .first()
    )
    if not report_run or not report_run.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report run not found")
    content_type = (
        "text/csv"
        if report_run.file_type == ReportFileType.csv
        else "application/pdf"
    )
    extension = report_run.file_type.value if report_run.file_type else "bin"
    return FileResponse(
        report_run.storage_path,
        media_type=content_type,
        filename=f"report-{report_run.id}.{extension}",
    )


@router.post("/{report_id}/share", response_model=ReportShareResponse, status_code=status.HTTP_201_CREATED)
def create_share_link(
    report_id: UUID,
    payload: ReportShareCreate,
    request: Request,
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    team_id = get_effective_team_id(team_api_key)
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == report_id, SavedReport.team_id == team_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    expires_in_days = payload.expires_in_days or settings.REPORT_SHARE_DEFAULT_TTL_DAYS
    max_days = settings.REPORT_SHARE_MAX_TTL_DAYS
    if expires_in_days > max_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"expires_in_days cannot exceed {max_days}",
        )
    token = secrets.token_urlsafe(32)
    share = ReportShareLink(
        team_id=team_id,
        report_id=report.id,
        token_hash=_hash_token(token),
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    base_url = settings.REPORT_SHARE_BASE_URL or str(request.base_url).rstrip("/")
    share_url = f"{base_url}/share/{token}"
    return ReportShareResponse(
        id=share.id,
        report_id=share.report_id,
        team_id=share.team_id,
        expires_at=share.expires_at,
        created_at=share.created_at,
        share_url=share_url,
    )
