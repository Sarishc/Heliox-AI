"""Tests for saved reports and exports."""
from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes.reports import create_report, get_report, list_reports
from app.api.routes.share import get_shared_report
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job
from app.models.reporting import ReportShareLink
from app.models.team import Team
from app.schemas.reporting import ReportConfig, ReportFilters, ReportSection, SavedReportCreate
from app.services import reports as reports_service
from app.services.reports import ReportService


def _api_key(team_id):
    return type("obj", (), {"team_id": team_id})()


def _seed_report(db_session, team_id):
    config = ReportConfig(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        filters=ReportFilters(environment="prod"),
        sections=[
            ReportSection.overview_kpis,
            ReportSection.daily_spend,
            ReportSection.idle_waste,
            ReportSection.top_models,
            ReportSection.top_recommendations,
        ],
    )
    payload = SavedReportCreate(name="Board Report", description="Q1 summary", config=config)
    report = create_report(payload=payload, db=db_session, auth_ctx=_api_key(team_id))
    return report


def _seed_metrics(db_session, team_id):
    for offset, amount in enumerate([100, 120, 80]):
        snapshot_date = date(2026, 1, 1) + timedelta(days=offset)
        db_session.add(
            CostSnapshot(
                team_id=team_id,
                date=snapshot_date,
                provider="aws",
                gpu_type="a100",
                cost_usd=amount,
            )
        )
        db_session.add(
            UsageSnapshot(
                team_id=team_id,
                date=snapshot_date,
                provider="aws",
                gpu_type="a100",
                environment="prod",
                project="ml",
                gpu_hours=8,
            )
        )
    db_session.add(
        Job(
            job_id="job-123",
            team_id=team_id,
            model_name="bert",
            provider="aws",
            gpu_type="a100",
            environment="prod",
            start_time=datetime(2026, 1, 2, 9, 0, 0),
            end_time=datetime(2026, 1, 2, 11, 0, 0),
            status="completed",
        )
    )
    db_session.commit()


def test_report_tenant_isolation(db_session):
    team_a = Team(name="Team A")
    team_b = Team(name="Team B")
    db_session.add_all([team_a, team_b])
    db_session.commit()

    report_a = _seed_report(db_session, team_a.id)
    _seed_report(db_session, team_b.id)

    results = list_reports(db=db_session, team_api_key=_api_key(team_a.id))
    assert len(results) == 1
    assert results[0].team_id == team_a.id

    with pytest.raises(HTTPException) as exc:
        get_report(report_id=report_a.id, db=db_session, team_api_key=_api_key(team_b.id))
    assert exc.value.status_code == 404


def test_share_token_access_and_expiry(db_session):
    team = Team(name="Team Share")
    db_session.add(team)
    db_session.commit()

    report = _seed_report(db_session, team.id)
    _seed_metrics(db_session, team.id)

    token = "token-value"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    link = ReportShareLink(
        team_id=team.id,
        report_id=report.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=1),
    )
    db_session.add(link)
    db_session.commit()

    response = get_shared_report(token=token, db=db_session)
    assert response.id == report.id

    link.expires_at = datetime.utcnow() - timedelta(days=1)
    db_session.add(link)
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        get_shared_report(token=token, db=db_session)
    assert exc.value.status_code == 404


def test_report_csv_schema(db_session, tmp_path, monkeypatch):
    team = Team(name="CSV Team")
    db_session.add(team)
    db_session.commit()

    report = _seed_report(db_session, team.id)
    _seed_metrics(db_session, team.id)

    monkeypatch.setattr(reports_service.settings, "REPORT_STORAGE_PATH", str(tmp_path))
    service = ReportService(db_session)
    run = service.generate_report(team_id=team.id, report=report, file_type="csv")
    assert run.storage_path
    contents = Path(run.storage_path).read_text(encoding="utf-8")
    assert "# Overview KPIs" in contents
    assert "metric,value" in contents
    assert "# Daily Spend" in contents
    assert "date,spend_usd" in contents
    assert "# Top Models" in contents


def test_report_pdf_generation(db_session, tmp_path, monkeypatch):
    team = Team(name="PDF Team")
    db_session.add(team)
    db_session.commit()

    report = _seed_report(db_session, team.id)
    _seed_metrics(db_session, team.id)

    monkeypatch.setattr(reports_service.settings, "REPORT_STORAGE_PATH", str(tmp_path))
    service = ReportService(db_session)
    run = service.generate_report(team_id=team.id, report=report, file_type="pdf")
    assert run.storage_path
    assert Path(run.storage_path).exists()
    assert Path(run.storage_path).stat().st_size > 0
