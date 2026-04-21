"""Tests for anomaly detection endpoint."""

from datetime import date, timedelta
from decimal import Decimal

from app.models.cost import CostSnapshot
from app.models.team import Team
from app.services.anomaly import AnomalyDetectionService


def test_anomaly_detection_basic(db_session):
    team = Team(name="Anomaly Team")
    db_session.add(team)
    db_session.commit()

    start = date(2026, 1, 1)
    for i in range(10):
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=start + timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                cost_usd=Decimal("100.00"),
            )
        )
    db_session.commit()

    service = AnomalyDetectionService(db_session)
    result = service.detect(team_id=team.id)
    assert result.projected_monthly_spend >= 0
