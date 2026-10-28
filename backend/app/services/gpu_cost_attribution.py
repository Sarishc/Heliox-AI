"""
GPU cost attribution and idle waste: the one place these numbers are computed.

The analytics routes, reports, recommendations, the optimizer and the assistant
all call this module, so the dashboard, exports and chat can't disagree.

Attribution
    Each day's spend for a (provider, gpu_type) is split between models by the
    job GPU-seconds that overlap that day on the same provider and GPU type.
    Jobs spanning midnight are split across days. Spend with no matching jobs
    is "unattributed", so models + unattributed always equals total spend.
    Each job is counted as one GPU (the jobs table has no GPU count).

Idle waste
    For each (day, provider, gpu_type): idle = cost x (1 - busy / allocated),
    where busy and allocated GPU-hours come from the agent. Spend with no
    allocated hours is "unmeasured", not idle: billing data alone says nothing
    about utilization.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job

METHOD = "gpu-cost-attribution/2026-10-27"

Key = Tuple[date, str, str]  # (day, provider, gpu_type)


def _norm(value: Optional[str]) -> str:
    return (value or "").lower().strip()


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _daily_costs(db: Session, team_id: Optional[UUID], start: date, end: date) -> Dict[Key, float]:
    stmt = (
        select(CostSnapshot.date, CostSnapshot.provider, CostSnapshot.gpu_type, func.sum(CostSnapshot.cost_usd))
        .where(CostSnapshot.date >= start, CostSnapshot.date <= end)
        .group_by(CostSnapshot.date, CostSnapshot.provider, CostSnapshot.gpu_type)
    )
    if team_id is not None:
        stmt = stmt.where(CostSnapshot.team_id == team_id)
    costs: Dict[Key, float] = defaultdict(float)
    for day, provider, gpu_type, cost in db.execute(stmt).all():
        costs[(day, _norm(provider), _norm(gpu_type))] += float(cost or 0)
    return costs


# ── Attribution ────────────────────────────────────────────────────────────────


@dataclass
class ModelCost:
    model_name: str
    cost_usd: float = 0.0
    job_count: int = 0
    gpu_hours: float = 0.0


@dataclass
class CostAttribution:
    models: List[ModelCost]
    unattributed_usd: float
    total_usd: float

    @property
    def total_gpu_hours(self) -> float:
        return sum(m.gpu_hours for m in self.models)


def attribute_cost_by_model(
    db: Session, team_id: UUID, start: date, end: date, now: Optional[datetime] = None
) -> CostAttribution:
    """Split spend in [start, end] between models; see the module docstring."""
    now = _naive_utc(now or datetime.now(timezone.utc))
    window_start = datetime.combine(start, time.min)
    window_end = datetime.combine(end + timedelta(days=1), time.min)

    costs = _daily_costs(db, team_id, start, end)
    jobs = (
        db.query(Job)
        .filter(
            Job.team_id == team_id,
            Job.start_time.isnot(None),
            Job.start_time < window_end,
            or_(Job.end_time.is_(None), Job.end_time > window_start),
        )
        .all()
    )

    models: Dict[str, ModelCost] = {}
    seconds: Dict[Key, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for job in jobs:
        job_start = max(_naive_utc(job.start_time), window_start)
        # Still-running jobs count up to now
        job_end = min(_naive_utc(job.end_time) if job.end_time else now, window_end)
        if job_end < job_start:
            continue
        # A zero-length job is still listed under its model, with no GPU-seconds to attribute
        model = models.setdefault(job.model_name, ModelCost(job.model_name))
        model.job_count += 1
        model.gpu_hours += (job_end - job_start).total_seconds() / 3600

        day_start = datetime.combine(job_start.date(), time.min)
        while day_start < job_end:
            day_end = day_start + timedelta(days=1)
            overlap = (min(job_end, day_end) - max(job_start, day_start)).total_seconds()
            if overlap > 0:
                key = (day_start.date(), _norm(job.provider), _norm(job.gpu_type))
                seconds[key][job.model_name] += overlap
            day_start = day_end

    unattributed = 0.0
    for key, cost in costs.items():
        by_model = seconds.get(key)
        total_seconds = sum(by_model.values()) if by_model else 0.0
        if total_seconds <= 0:
            unattributed += cost
            continue
        for model_name, model_seconds in by_model.items():
            models[model_name].cost_usd += cost * model_seconds / total_seconds

    ordered = sorted(models.values(), key=lambda m: (-m.cost_usd, m.model_name))
    return CostAttribution(models=ordered, unattributed_usd=unattributed, total_usd=sum(costs.values()))


# ── Idle waste ─────────────────────────────────────────────────────────────────


@dataclass
class GpuGroupUsage:
    """Window totals for one (provider, gpu_type)."""

    provider: str
    gpu_type: str
    cost_usd: float = 0.0
    measured_cost_usd: float = 0.0
    busy_hours: float = 0.0
    allocated_hours: float = 0.0
    idle_waste_usd: float = 0.0
    days: int = 0  # days with spend
    measured_days: int = 0  # days with spend and agent data

    @property
    def utilization(self) -> Optional[float]:
        """Busy / allocated over measured days; None when the agent never reported."""
        if self.allocated_hours <= 0:
            return None
        return min(self.busy_hours / self.allocated_hours, 1.0)


@dataclass
class IdleWaste:
    groups: List[GpuGroupUsage] = field(default_factory=list)

    @property
    def idle_waste_usd(self) -> float:
        return sum(g.idle_waste_usd for g in self.groups)

    @property
    def total_cost_usd(self) -> float:
        return sum(g.cost_usd for g in self.groups)

    @property
    def measured_cost_usd(self) -> float:
        return sum(g.measured_cost_usd for g in self.groups)

    @property
    def unmeasured_cost_usd(self) -> float:
        return self.total_cost_usd - self.measured_cost_usd

    @property
    def busy_hours(self) -> float:
        return sum(g.busy_hours for g in self.groups)

    @property
    def allocated_hours(self) -> float:
        return sum(g.allocated_hours for g in self.groups)

    @property
    def coverage(self) -> float:
        """Share of spend we have utilization data for."""
        total = self.total_cost_usd
        return self.measured_cost_usd / total if total > 0 else 0.0


def measure_idle_waste(db: Session, team_id: Optional[UUID], start: date, end: date) -> IdleWaste:
    """Idle waste per (provider, gpu_type) over [start, end]; see the module docstring."""
    costs = _daily_costs(db, team_id, start, end)

    usage_stmt = (
        select(
            UsageSnapshot.date,
            UsageSnapshot.provider,
            UsageSnapshot.gpu_type,
            func.sum(UsageSnapshot.gpu_hours),
            func.sum(UsageSnapshot.allocated_gpu_hours),
        )
        .where(UsageSnapshot.date >= start, UsageSnapshot.date <= end)
        .group_by(UsageSnapshot.date, UsageSnapshot.provider, UsageSnapshot.gpu_type)
    )
    if team_id is not None:
        usage_stmt = usage_stmt.where(UsageSnapshot.team_id == team_id)
    usage: Dict[Key, Tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
    for day, provider, gpu_type, busy, allocated in db.execute(usage_stmt).all():
        key = (day, _norm(provider), _norm(gpu_type))
        prev_busy, prev_allocated = usage[key]
        usage[key] = (prev_busy + float(busy or 0), prev_allocated + float(allocated or 0))

    groups: Dict[Tuple[str, str], GpuGroupUsage] = {}
    for (day, provider, gpu_type), cost in sorted(costs.items()):
        group = groups.setdefault((provider, gpu_type), GpuGroupUsage(provider, gpu_type))
        group.cost_usd += cost
        group.days += 1
        busy, allocated = usage.get((day, provider, gpu_type), (0.0, 0.0))
        if allocated <= 0:
            continue
        busy = min(busy, allocated)
        group.measured_cost_usd += cost
        group.busy_hours += busy
        group.allocated_hours += allocated
        group.idle_waste_usd += cost * (1 - busy / allocated)
        group.measured_days += 1

    return IdleWaste(groups=sorted(groups.values(), key=lambda g: (-g.cost_usd, g.provider, g.gpu_type)))
