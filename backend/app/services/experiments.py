"""Services for optimization experiments."""

import logging
from datetime import date
from typing import Dict, List
from uuid import UUID

import random
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot
from app.models.experiment import Experiment, ExperimentAssignment, ExperimentResult
from app.models.job import Job

logger = logging.getLogger(__name__)


class ExperimentService:
    def __init__(self, db: Session):
        self.db = db

    def create_experiment(
        self,
        *,
        team_id: UUID,
        name: str,
        baseline_policy: str,
        optimized_policy: str,
        start_date: date,
        end_date: date,
        assignment_ratio: float,
    ) -> Experiment:
        experiment = Experiment(
            team_id=team_id,
            name=name,
            baseline_policy=baseline_policy,
            optimized_policy=optimized_policy,
            start_date=start_date,
            end_date=end_date,
            status="created",
        )
        self.db.add(experiment)
        self.db.flush()

        jobs = (
            self.db.query(Job)
            .filter(
                Job.team_id == team_id,
                Job.start_time.isnot(None),
                func.date(Job.start_time) >= start_date,
                func.date(Job.start_time) <= end_date,
            )
            .all()
        )

        rng = random.Random(str(experiment.id))
        assignments: List[ExperimentAssignment] = []
        for job in jobs:
            group = "baseline" if rng.random() < assignment_ratio else "optimized"
            assignments.append(ExperimentAssignment(experiment_id=experiment.id, job_id=job.id, group=group))

        self.db.bulk_save_objects(assignments)
        self.db.commit()
        self.db.refresh(experiment)
        return experiment

    def compute_results(self, *, experiment: Experiment) -> ExperimentResult:
        assignments = (
            self.db.query(ExperimentAssignment)
            .join(Job, Job.id == ExperimentAssignment.job_id)
            .filter(ExperimentAssignment.experiment_id == experiment.id)
            .all()
        )
        if not assignments:
            metrics = {
                "baseline": {},
                "optimized": {},
                "summary": {"message": "No jobs assigned"},
            }
            result = ExperimentResult(experiment_id=experiment.id, metrics=metrics)
            self.db.add(result)
            self.db.commit()
            return result

        job_ids = [a.job_id for a in assignments]
        jobs = {job.id: job for job in self.db.query(Job).filter(Job.id.in_(job_ids)).all()}

        day_costs = dict(
            self.db.execute(
                select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd))
                .where(
                    CostSnapshot.team_id == experiment.team_id,
                    CostSnapshot.date >= experiment.start_date,
                    CostSnapshot.date <= experiment.end_date,
                )
                .group_by(CostSnapshot.date)
            ).all()
        )

        day_job_counts: Dict[date, int] = {}
        for assignment in assignments:
            job = jobs.get(assignment.job_id)
            if not job or not job.start_time:
                continue
            day = job.start_time.date()
            day_job_counts[day] = day_job_counts.get(day, 0) + 1

        metrics = {
            "baseline": self._group_metrics(assignments, jobs, day_costs, day_job_counts, "baseline"),
            "optimized": self._group_metrics(assignments, jobs, day_costs, day_job_counts, "optimized"),
        }
        summary = self._summary_metrics(metrics["baseline"], metrics["optimized"])
        metrics["summary"] = summary

        existing = self.db.query(ExperimentResult).filter(ExperimentResult.experiment_id == experiment.id).first()
        if existing:
            existing.metrics = metrics
            self.db.commit()
            return existing

        result = ExperimentResult(experiment_id=experiment.id, metrics=metrics)
        self.db.add(result)
        self.db.commit()
        return result

    def _group_metrics(
        self,
        assignments: List[ExperimentAssignment],
        jobs: Dict[UUID, Job],
        day_costs: Dict[date, float],
        day_job_counts: Dict[date, int],
        group: str,
    ) -> Dict:
        total_cost = 0.0
        total_runtime = 0.0
        runtime_count = 0
        job_count = 0

        for assignment in assignments:
            if assignment.group != group:
                continue
            job = jobs.get(assignment.job_id)
            if not job or not job.start_time:
                continue
            job_count += 1
            day = job.start_time.date()
            day_cost = float(day_costs.get(day, 0.0))
            day_jobs = day_job_counts.get(day, 0)
            if day_jobs > 0:
                total_cost += day_cost * (1 / day_jobs)
            if job.end_time and job.start_time:
                runtime_hours = (job.end_time - job.start_time).total_seconds() / 3600.0
                total_runtime += runtime_hours
                runtime_count += 1

        avg_runtime = total_runtime / runtime_count if runtime_count else None
        avg_cost = total_cost / job_count if job_count else 0.0
        return {
            "job_count": job_count,
            "total_cost": round(total_cost, 2),
            "avg_cost_per_job": round(avg_cost, 2),
            "avg_runtime_hours": (round(avg_runtime, 2) if avg_runtime is not None else None),
        }

    @staticmethod
    def _summary_metrics(baseline: Dict, optimized: Dict) -> Dict:
        base_cost = baseline.get("total_cost") or 0.0
        opt_cost = optimized.get("total_cost") or 0.0
        base_runtime = baseline.get("avg_runtime_hours")
        opt_runtime = optimized.get("avg_runtime_hours")

        cost_delta_pct = None
        if base_cost > 0:
            cost_delta_pct = round((opt_cost - base_cost) / base_cost, 4)

        runtime_delta_pct = None
        if base_runtime and base_runtime > 0 and opt_runtime is not None:
            runtime_delta_pct = round((opt_runtime - base_runtime) / base_runtime, 4)

        return {
            "cost_delta_pct": cost_delta_pct,
            "runtime_delta_pct": runtime_delta_pct,
        }
