"""Tests for team-scoped ingestion."""

from datetime import datetime, date
from decimal import Decimal

from app.models.team import Team
from app.services.cost_ingestion import CostIngestionService, CostDataRecord
from app.services.usage_ingestion import UsageIngestionService
from app.schemas.ingest import UsageMetric
from app.models.cost import CostSnapshot, UsageSnapshot


def test_cost_ingestion_sets_team_id(db_session):
    team = Team(name="Ingest Team")
    db_session.add(team)
    db_session.commit()

    service = CostIngestionService(db_session)
    records = [
        CostDataRecord(
            team_id=str(team.id),
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("100.00"),
        )
    ]
    result = service.ingest_cost_records(records=records, team_id=str(team.id))
    assert result.inserted == 1

    snapshot = db_session.query(CostSnapshot).first()
    assert snapshot.team_id == team.id


def test_usage_ingestion_sets_team_id(db_session):
    team = Team(name="Usage Team")
    db_session.add(team)
    db_session.commit()

    service = UsageIngestionService(db_session)
    metrics = [
        UsageMetric(
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal("1.5"),
            tags={"cluster": "test"},
        )
    ]
    result = service.ingest_usage_metrics(team_id=team.id, metrics=metrics)
    assert result["inserted"] == 1
    usage = db_session.query(UsageSnapshot).first()
    assert usage.team_id == team.id


def test_small_agent_reports_are_not_rounded_away(db_session):
    """The agent reports every 60s; a 25%-busy GPU sends ~0.0042 GPU-hours per report."""
    team = Team(name="Precision Team")
    db_session.add(team)
    db_session.commit()

    service = UsageIngestionService(db_session)
    for minute in range(4):
        service.ingest_usage_metrics(
            team_id=team.id,
            metrics=[
                UsageMetric(
                    timestamp=datetime(2026, 1, 1, 12, minute, 0),
                    provider="aws",
                    gpu_type="a100",
                    gpu_hours=Decimal("0.004167"),
                )
            ],
        )

    usage = db_session.query(UsageSnapshot).filter(UsageSnapshot.team_id == team.id).one()
    assert usage.gpu_hours == Decimal("0.016668")
