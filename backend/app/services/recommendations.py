"""Recommendation engine for Heliox-AI cost optimization."""
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import logging
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job
from app.models.team import Team
from app.schemas.recommendation import (
    Recommendation,
    RecommendationEvidence,
    RecommendationFilters,
    RecommendationResponse,
    RecommendationSeverity,
    RecommendationType,
)

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Rules-based recommendation engine for cost optimization.
    
    This engine analyzes job execution patterns, GPU usage, and costs
    to generate actionable recommendations for reducing waste and
    optimizing infrastructure spending.
    """
    
    # Configuration constants
    LONG_RUNNING_JOB_THRESHOLD_HOURS = 24  # Jobs longer than 24 hours
    IDLE_GPU_THRESHOLD_PERCENTAGE = 30  # GPU usage below 30% is considered idle
    OFF_HOURS_START = time(18, 0)  # 6 PM
    OFF_HOURS_END = time(9, 0)  # 9 AM
    HOURLY_GPU_COST_ESTIMATE = 3.50  # Rough estimate for savings calculations
    
    def __init__(self, db: Session):
        """
        Initialize the recommendation engine.
        
        Args:
            db: Database session
        """
        self.db = db
    
    def generate_recommendations(
        self, filters: RecommendationFilters
    ) -> RecommendationResponse:
        """
        Generate all recommendations based on filters.
        
        Args:
            filters: Filters for recommendation generation
            
        Returns:
            RecommendationResponse with recommendations and summary
        """
        logger.info(
            f"Generating recommendations for date range: "
            f"{filters.start_date} to {filters.end_date}"
        )
        
        recommendations: List[Recommendation] = []
        
        try:
            # Rule 1: Detect idle GPU spend
            idle_gpu_recs = self._detect_idle_gpu_spend(
                filters.start_date, filters.end_date, filters.team_id
            )
            recommendations.extend(idle_gpu_recs)
            logger.info(f"Generated {len(idle_gpu_recs)} idle GPU recommendations")
            
            # Rule 2: Detect long-running jobs
            long_running_recs = self._detect_long_running_jobs(
                filters.start_date, filters.end_date, filters.team_id
            )
            recommendations.extend(long_running_recs)
            logger.info(f"Generated {len(long_running_recs)} long-running job recommendations")
            
            # Rule 3: Detect off-hours opportunities
            off_hours_recs = self._detect_off_hours_jobs(
                filters.start_date, filters.end_date, filters.team_id
            )
            recommendations.extend(off_hours_recs)
            logger.info(f"Generated {len(off_hours_recs)} off-hours recommendations")
            
            # Apply filters
            recommendations = self._apply_filters(recommendations, filters)
            
            # Calculate summary
            summary = self._calculate_summary(recommendations)
            total_savings = sum(r.estimated_savings_usd for r in recommendations)
            
            logger.info(
                f"Generated {len(recommendations)} total recommendations "
                f"with ${total_savings:,.2f} potential savings"
            )
            
            return RecommendationResponse(
                recommendations=recommendations,
                summary=summary,
                date_range={
                    "start_date": str(filters.start_date),
                    "end_date": str(filters.end_date),
                },
                total_estimated_savings_usd=total_savings,
            )
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}", exc_info=True)
            # Return empty response on error
            return RecommendationResponse(
                recommendations=[],
                summary={"error": str(e)},
                date_range={
                    "start_date": str(filters.start_date),
                    "end_date": str(filters.end_date),
                },
                total_estimated_savings_usd=0.0,
            )
    
    def _detect_idle_gpu_spend(
        self, start_date: date, end_date: date, team_id: Optional[str] = None
    ) -> List[Recommendation]:
        """
        Detect idle GPU spend by comparing usage hours to expected usage.
        
        If UsageSnapshot shows GPU hours significantly lower than what
        we'd expect from the cost, flag it as potential waste.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            team_id: Optional team filter
            
        Returns:
            List of idle GPU recommendations
        """
        recommendations = []
        
        try:
            # Get cost data aggregated by gpu_type and provider
            cost_stmt = (
                select(
                    CostSnapshot.gpu_type,
                    CostSnapshot.provider,
                    func.sum(CostSnapshot.cost_usd).label("total_cost"),
                    func.count(CostSnapshot.id).label("days_count"),
                )
                .where(
                    CostSnapshot.date >= start_date,
                    CostSnapshot.date <= end_date,
                )
                .group_by(CostSnapshot.gpu_type, CostSnapshot.provider)
            )
            
            cost_results = self.db.execute(cost_stmt).all()
            
            for gpu_type, provider, total_cost, days_count in cost_results:
                # Get usage data for the same GPU type and provider
                usage_stmt = (
                    select(func.sum(UsageSnapshot.gpu_hours))
                    .where(
                        UsageSnapshot.date >= start_date,
                        UsageSnapshot.date <= end_date,
                        UsageSnapshot.gpu_type == gpu_type,
                        UsageSnapshot.provider == provider,
                    )
                )
                
                actual_usage = self.db.execute(usage_stmt).scalar_one_or_none() or 0.0
                
                # Estimate expected usage based on cost
                # Assume 24/7 availability for the period
                expected_hours_per_day = 24
                expected_total_hours = days_count * expected_hours_per_day
                
                # Calculate waste percentage
                if expected_total_hours > 0:
                    utilization_pct = (actual_usage / expected_total_hours) * 100
                    waste_pct = 100 - utilization_pct
                    
                    # Flag if utilization is below threshold
                    if utilization_pct < self.IDLE_GPU_THRESHOLD_PERCENTAGE:
                        # Estimate savings (wasted hours * cost per hour)
                        wasted_hours = expected_total_hours - actual_usage
                        estimated_savings = wasted_hours * self.HOURLY_GPU_COST_ESTIMATE
                        
                        severity = self._determine_severity_by_waste(waste_pct)
                        
                        recommendations.append(
                            Recommendation(
                                type=RecommendationType.IDLE_GPU,
                                title=f"Idle {gpu_type.upper()} GPUs on {provider.upper()}",
                                description=(
                                    f"Detected {waste_pct:.1f}% idle GPU capacity on {provider.upper()} "
                                    f"{gpu_type.upper()} instances. You're paying for {expected_total_hours:.0f} "
                                    f"hours but only using {actual_usage:.0f} hours. "
                                    f"Consider scaling down or right-sizing your GPU allocation."
                                ),
                                severity=severity,
                                estimated_savings_usd=round(estimated_savings, 2),
                                evidence=RecommendationEvidence(
                                    date_range={
                                        "start_date": str(start_date),
                                        "end_date": str(end_date),
                                    },
                                    total_cost_usd=float(total_cost),
                                    expected_usage_hours=expected_total_hours,
                                    actual_usage_hours=actual_usage,
                                    waste_percentage=round(waste_pct, 2),
                                    gpu_type=gpu_type,
                                    provider=provider,
                                ),
                            )
                        )
                        
        except Exception as e:
            logger.error(f"Error detecting idle GPU spend: {e}", exc_info=True)
        
        return recommendations
    
    def _detect_long_running_jobs(
        self, start_date: date, end_date: date, team_id: Optional[str] = None
    ) -> List[Recommendation]:
        """
        Detect jobs that run for an unusually long time.
        
        Long-running jobs may indicate inefficient code, lack of optimization,
        or opportunities for right-sizing or better scheduling.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            team_id: Optional team filter
            
        Returns:
            List of long-running job recommendations
        """
        recommendations = []
        
        try:
            # Query for completed jobs with runtime calculation
            stmt = (
                select(Job, Team.name)
                .join(Team, Job.team_id == Team.id)
                .where(
                    func.date(Job.start_time) >= start_date,
                    func.date(Job.start_time) <= end_date,
                    Job.end_time.isnot(None),
                    Job.status == "completed",
                )
            )
            
            if team_id:
                stmt = stmt.where(Job.team_id == team_id)
            
            results = self.db.execute(stmt).all()
            
            for job, team_name in results:
                runtime_delta = job.end_time - job.start_time
                runtime_hours = runtime_delta.total_seconds() / 3600
                
                # Flag if runtime exceeds threshold
                if runtime_hours > self.LONG_RUNNING_JOB_THRESHOLD_HOURS:
                    # Estimate potential savings from optimization (e.g., 20% reduction)
                    potential_reduction_hours = runtime_hours * 0.20
                    estimated_savings = potential_reduction_hours * self.HOURLY_GPU_COST_ESTIMATE
                    
                    severity = self._determine_severity_by_runtime(runtime_hours)
                    
                    recommendations.append(
                        Recommendation(
                            type=RecommendationType.LONG_RUNNING_JOB,
                            title=f"Long-running job: {job.model_name} ({team_name})",
                            description=(
                                f"Job {job.job_id} ran for {runtime_hours:.1f} hours, "
                                f"exceeding the {self.LONG_RUNNING_JOB_THRESHOLD_HOURS}h threshold. "
                                f"Consider optimizing the model training code, using distributed "
                                f"training, or right-sizing the GPU instance. A 20% reduction "
                                f"could save approximately ${estimated_savings:.2f}."
                            ),
                            severity=severity,
                            estimated_savings_usd=round(estimated_savings, 2),
                            evidence=RecommendationEvidence(
                                date_range={
                                    "start_date": str(start_date),
                                    "end_date": str(end_date),
                                },
                                job_id=job.job_id,
                                job_runtime_hours=round(runtime_hours, 2),
                                job_start_time=job.start_time,
                                job_end_time=job.end_time,
                                gpu_type=job.gpu_type,
                                provider=job.provider,
                                team_name=team_name,
                                model_name=job.model_name,
                            ),
                        )
                    )
                    
        except Exception as e:
            logger.error(f"Error detecting long-running jobs: {e}", exc_info=True)
        
        return recommendations
    
    def _detect_off_hours_jobs(
        self, start_date: date, end_date: date, team_id: Optional[str] = None
    ) -> List[Recommendation]:
        """
        Detect jobs running during peak business hours (9am-6pm weekdays).
        
        These jobs could potentially be scheduled for off-peak hours
        to take advantage of lower costs or reserved capacity.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            team_id: Optional team filter
            
        Returns:
            List of off-hours scheduling recommendations
        """
        recommendations = []
        
        try:
            # Query for jobs that started during business hours
            stmt = (
                select(Job, Team.name)
                .join(Team, Job.team_id == Team.id)
                .where(
                    func.date(Job.start_time) >= start_date,
                    func.date(Job.start_time) <= end_date,
                    Job.start_time.isnot(None),
                )
            )
            
            if team_id:
                stmt = stmt.where(Job.team_id == team_id)
            
            results = self.db.execute(stmt).all()
            
            # Group by team to avoid too many individual recommendations
            team_business_hours_jobs: Dict[str, List[Job]] = {}
            
            for job, team_name in results:
                job_start_time = job.start_time.time()
                job_weekday = job.start_time.weekday()  # 0=Monday, 6=Sunday
                
                # Check if started during business hours (9am-6pm) on weekdays
                is_weekday = job_weekday < 5  # Monday-Friday
                is_business_hours = (
                    self.OFF_HOURS_END <= job_start_time < self.OFF_HOURS_START
                )
                
                if is_weekday and is_business_hours:
                    if team_name not in team_business_hours_jobs:
                        team_business_hours_jobs[team_name] = []
                    team_business_hours_jobs[team_name].append(job)
            
            # Create recommendations per team
            for team_name, jobs in team_business_hours_jobs.items():
                if len(jobs) >= 3:  # Only recommend if there are 3+ jobs
                    # Calculate total runtime
                    total_runtime_hours = 0
                    for job in jobs:
                        if job.end_time:
                            runtime_delta = job.end_time - job.start_time
                            total_runtime_hours += runtime_delta.total_seconds() / 3600
                    
                    # Estimate potential savings (conservative 10% from off-peak pricing)
                    estimated_savings = total_runtime_hours * self.HOURLY_GPU_COST_ESTIMATE * 0.10
                    
                    recommendations.append(
                        Recommendation(
                            type=RecommendationType.OFF_HOURS_USAGE,
                            title=f"Consider off-peak scheduling for {team_name}",
                            description=(
                                f"Team '{team_name}' ran {len(jobs)} jobs during business hours "
                                f"(9am-6pm weekdays). Consider scheduling non-urgent training jobs "
                                f"during off-peak hours (evenings/weekends) to potentially access "
                                f"discounted pricing or reserved capacity. This could save approximately "
                                f"${estimated_savings:.2f} through off-peak pricing."
                            ),
                            severity=RecommendationSeverity.LOW,
                            estimated_savings_usd=round(estimated_savings, 2),
                            evidence=RecommendationEvidence(
                                date_range={
                                    "start_date": str(start_date),
                                    "end_date": str(end_date),
                                },
                                team_name=team_name,
                                metadata={
                                    "business_hours_job_count": len(jobs),
                                    "total_runtime_hours": round(total_runtime_hours, 2),
                                },
                            ),
                        )
                    )
                    
        except Exception as e:
            logger.error(f"Error detecting off-hours opportunities: {e}", exc_info=True)
        
        return recommendations
    
    def _determine_severity_by_waste(self, waste_percentage: float) -> RecommendationSeverity:
        """Determine severity based on waste percentage."""
        if waste_percentage >= 70:
            return RecommendationSeverity.HIGH
        elif waste_percentage >= 50:
            return RecommendationSeverity.MEDIUM
        else:
            return RecommendationSeverity.LOW
    
    def _determine_severity_by_runtime(self, runtime_hours: float) -> RecommendationSeverity:
        """Determine severity based on job runtime."""
        if runtime_hours >= 72:  # 3+ days
            return RecommendationSeverity.HIGH
        elif runtime_hours >= 48:  # 2+ days
            return RecommendationSeverity.MEDIUM
        else:
            return RecommendationSeverity.LOW
    
    def _apply_filters(
        self, recommendations: List[Recommendation], filters: RecommendationFilters
    ) -> List[Recommendation]:
        """Apply post-generation filters to recommendations."""
        filtered = recommendations
        
        # Filter by minimum severity
        if filters.min_severity:
            severity_order = {
                RecommendationSeverity.LOW: 1,
                RecommendationSeverity.MEDIUM: 2,
                RecommendationSeverity.HIGH: 3,
            }
            min_severity_level = severity_order[filters.min_severity]
            filtered = [
                r for r in filtered
                if severity_order[r.severity] >= min_severity_level
            ]
        
        # Filter by types
        if filters.types:
            filtered = [r for r in filtered if r.type in filters.types]
        
        # Filter by minimum savings
        if filters.min_savings:
            filtered = [r for r in filtered if r.estimated_savings_usd >= filters.min_savings]
        
        return filtered
    
    def _calculate_summary(self, recommendations: List[Recommendation]) -> Dict:
        """Calculate summary statistics for recommendations."""
        if not recommendations:
            return {
                "total": 0,
                "by_severity": {},
                "by_type": {},
            }
        
        by_severity = {}
        by_type = {}
        
        for rec in recommendations:
            # Count by severity
            severity_key = rec.severity.value
            by_severity[severity_key] = by_severity.get(severity_key, 0) + 1
            
            # Count by type
            type_key = rec.type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1
        
        return {
            "total": len(recommendations),
            "by_severity": by_severity,
            "by_type": by_type,
        }

