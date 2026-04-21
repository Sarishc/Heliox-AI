"""Tests for experiment framework."""

from datetime import date, timedelta
from decimal import Decimal

from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.team import Team
from app.services.experiments import ExperimentService


def test_experiment_results(db_session):
    team = Team(name="Experiment Team")
    db_session.add(team)
    db_session.commit()

    start = date(2026, 1, 1)
    for i in range(6):
        db_session.add(
            Job(
                job_id=f"exp-job-{i}",
                team_id=team.id,
                model_name="bert",
                provider="aws",
                gpu_type="a100",
                start_time=start + timedelta(days=i),
                end_time=start + timedelta(days=i),
                status="completed",
            )
        )
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

    service = ExperimentService(db_session)
    experiment = service.create_experiment(
        team_id=team.id,
        name="Test Experiment",
        baseline_policy="baseline",
        optimized_policy="optimized",
        start_date=start,
        end_date=start + timedelta(days=5),
        assignment_ratio=0.5,
    )
    result = service.compute_results(experiment=experiment)
    assert result.metrics["baseline"]["job_count"] + result.metrics["optimized"]["job_count"] > 0
    assert "summary" in result.metrics
