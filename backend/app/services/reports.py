"""Report generation service for CSV/PDF exports."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job
from app.models.reporting import ReportFileType, ReportRun, ReportRunStatus, SavedReport
from app.schemas.recommendation import RecommendationFilters
from app.schemas.reporting import ReportConfig, ReportSection
from app.services.recommendations import RecommendationEngine

settings = get_settings()


class ReportService:
    """Generate report data and persist exports."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_report(self, team_id: UUID, report: SavedReport, file_type: str) -> ReportRun:
        run = ReportRun(
            team_id=team_id,
            report_id=report.id,
            status=ReportRunStatus.running,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            payload = self.build_report_payload(team_id=team_id, config=report.config_json)
            storage_path = self._write_report_file(
                team_id=team_id,
                report_id=report.id,
                run_id=run.id,
                file_type=file_type,
                payload=payload,
            )
            run.status = ReportRunStatus.completed
            run.generated_at = payload["generated_at"]
            run.storage_path = storage_path
            run.file_type = ReportFileType(file_type)
        except Exception:
            run.status = ReportRunStatus.failed
            self.db.add(run)
            self.db.commit()
            raise
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def build_report_payload(self, team_id: UUID, config: dict) -> dict[str, Any]:
        parsed_config = ReportConfig.model_validate(config)
        sections = parsed_config.sections or [
            ReportSection.overview_kpis,
            ReportSection.daily_spend,
            ReportSection.idle_waste,
            ReportSection.top_models,
            ReportSection.top_recommendations,
        ]
        start_date = parsed_config.start_date
        end_date = parsed_config.end_date
        data: dict[str, Any] = {}

        if ReportSection.overview_kpis in sections:
            total_spend = self._get_total_spend(team_id, start_date, end_date)
            idle_waste = self._get_idle_waste(team_id, start_date, end_date)
            recommended_savings = self._get_recommended_savings(team_id, start_date, end_date)
            data["overview_kpis"] = {
                "total_spend_usd": total_spend,
                "idle_waste_usd": idle_waste,
                "recommended_savings_usd": recommended_savings,
            }

        if ReportSection.daily_spend in sections:
            data["daily_spend"] = self._get_daily_spend(team_id, start_date, end_date)

        if ReportSection.idle_waste in sections:
            data["idle_waste"] = {"total_idle_waste_usd": self._get_idle_waste(team_id, start_date, end_date)}

        if ReportSection.top_models in sections:
            data["top_models"] = self._get_top_models(team_id, start_date, end_date)

        if ReportSection.top_recommendations in sections:
            data["top_recommendations"] = self._get_top_recommendations(team_id, start_date, end_date)

        return {
            "config": parsed_config,
            "generated_at": datetime.utcnow(),
            "data": data,
        }

    def _write_report_file(
        self,
        team_id: UUID,
        report_id: UUID,
        run_id: UUID,
        file_type: str,
        payload: dict[str, Any],
    ) -> str:
        base_path = Path(settings.REPORT_STORAGE_PATH) / str(team_id)
        base_path.mkdir(parents=True, exist_ok=True)
        filename = f"report-{report_id}-{run_id}.{file_type}"
        storage_path = base_path / filename
        if file_type == ReportFileType.csv.value:
            content = self._render_csv(payload)
            storage_path.write_text(content, encoding="utf-8")
        elif file_type == ReportFileType.pdf.value:
            self._render_pdf(payload, storage_path)
        else:
            raise ValueError("Unsupported report file type")
        return str(storage_path)

    def _render_csv(self, payload: dict[str, Any]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        data = payload["data"]

        if "overview_kpis" in data:
            writer.writerow(["# Overview KPIs"])
            writer.writerow(["metric", "value"])
            for key, value in data["overview_kpis"].items():
                writer.writerow([key, value])
            writer.writerow([])

        if "daily_spend" in data:
            writer.writerow(["# Daily Spend"])
            writer.writerow(["date", "spend_usd"])
            for row in data["daily_spend"]:
                writer.writerow([row["date"], row["spend_usd"]])
            writer.writerow([])

        if "idle_waste" in data:
            writer.writerow(["# Idle Waste"])
            writer.writerow(["metric", "value"])
            writer.writerow(["total_idle_waste_usd", data["idle_waste"]["total_idle_waste_usd"]])
            writer.writerow([])

        if "top_models" in data:
            writer.writerow(["# Top Models"])
            writer.writerow(["model_name", "total_cost_usd", "job_count"])
            for row in data["top_models"]:
                writer.writerow([row["model_name"], row["total_cost_usd"], row["job_count"]])
            writer.writerow([])

        if "top_recommendations" in data:
            writer.writerow(["# Top Recommendations"])
            writer.writerow(["title", "type", "estimated_savings_usd"])
            for row in data["top_recommendations"]:
                writer.writerow([row["title"], row["type"], row["estimated_savings_usd"]])
            writer.writerow([])

        return output.getvalue()

    def _render_pdf(self, payload: dict[str, Any], storage_path: Path) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(storage_path), pagesize=letter)
        story = []
        data = payload["data"]

        story.append(Paragraph("Heliox Report Summary", styles["Title"]))
        story.append(Paragraph(f"Generated at {payload['generated_at'].isoformat()} UTC", styles["Normal"]))
        story.append(Spacer(1, 12))

        if "overview_kpis" in data:
            story.append(Paragraph("Overview KPIs", styles["Heading2"]))
            table_data = [["Metric", "Value"]]
            for key, value in data["overview_kpis"].items():
                table_data.append([key.replace("_", " ").title(), f"{value}"])
            story.append(self._build_table(table_data))
            story.append(Spacer(1, 12))

        if "daily_spend" in data:
            story.append(Paragraph("Daily Spend", styles["Heading2"]))
            table_data = [["Date", "Spend (USD)"]]
            for row in data["daily_spend"]:
                table_data.append([row["date"], f"{row['spend_usd']}"])
            story.append(self._build_table(table_data))
            story.append(Spacer(1, 12))

        if "idle_waste" in data:
            story.append(Paragraph("Idle Waste", styles["Heading2"]))
            table_data = [["Metric", "Value"]]
            table_data.append(["Total Idle Waste (USD)", f"{data['idle_waste']['total_idle_waste_usd']}"])
            story.append(self._build_table(table_data))
            story.append(Spacer(1, 12))

        if "top_models" in data:
            story.append(Paragraph("Top Models", styles["Heading2"]))
            table_data = [["Model", "Total Cost (USD)", "Job Count"]]
            for row in data["top_models"]:
                table_data.append([row["model_name"], f"{row['total_cost_usd']}", f"{row['job_count']}"])
            story.append(self._build_table(table_data))
            story.append(Spacer(1, 12))

        if "top_recommendations" in data:
            story.append(Paragraph("Top Recommendations", styles["Heading2"]))
            table_data = [["Title", "Type", "Estimated Savings (USD)"]]
            for row in data["top_recommendations"]:
                table_data.append([row["title"], row["type"], f"{row['estimated_savings_usd']}"])
            story.append(self._build_table(table_data))
            story.append(Spacer(1, 12))

        doc.build(story)

    def _build_table(self, table_data: list[list[str]]) -> Any:
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle

        table = Table(table_data, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        return table

    def _get_total_spend(self, team_id: UUID, start: date, end: date) -> float:
        total_cost = self.db.execute(
            select(func.sum(CostSnapshot.cost_usd)).where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
        ).scalar_one_or_none() or 0.0
        return round(float(total_cost), 2)

    def _get_daily_spend(self, team_id: UUID, start: date, end: date) -> list[dict[str, Any]]:
        rows = self.db.execute(
            select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd))
            .where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
            .group_by(CostSnapshot.date)
            .order_by(CostSnapshot.date)
        ).all()
        spend_by_date = {row[0]: round(float(row[1] or 0.0), 2) for row in rows}
        results = []
        current = start
        while current <= end:
            results.append({"date": current.isoformat(), "spend_usd": spend_by_date.get(current, 0.0)})
            current += timedelta(days=1)
        return results

    def _get_idle_waste(self, team_id: UUID, start: date, end: date) -> float:
        cost_stmt = (
            select(
                CostSnapshot.gpu_type,
                CostSnapshot.provider,
                func.sum(CostSnapshot.cost_usd).label("total_cost"),
                func.count(CostSnapshot.id).label("days_count"),
            )
            .where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
            .group_by(CostSnapshot.gpu_type, CostSnapshot.provider)
        )
        idle_waste = 0.0
        for gpu_type, provider, cost_sum, days_count in self.db.execute(cost_stmt).all():
            expected_hours = float(days_count) * 24.0
            usage_hours = self.db.execute(
                select(func.sum(UsageSnapshot.gpu_hours)).where(
                    UsageSnapshot.team_id == team_id,
                    UsageSnapshot.date >= start,
                    UsageSnapshot.date <= end,
                    UsageSnapshot.gpu_type == gpu_type,
                    UsageSnapshot.provider == provider,
                )
            ).scalar_one_or_none() or 0.0
            if expected_hours > 0:
                waste_ratio = max(0.0, (expected_hours - float(usage_hours)) / expected_hours)
                idle_waste += float(cost_sum or 0.0) * waste_ratio
        return round(idle_waste, 2)

    def _get_recommended_savings(self, team_id: UUID, start: date, end: date) -> float:
        filters = RecommendationFilters(start_date=start, end_date=end, team_id=team_id)
        recs = RecommendationEngine(self.db).generate_recommendations(filters)
        return round(float(recs.total_estimated_savings_usd), 2)

    def _get_top_models(self, team_id: UUID, start: date, end: date) -> list[dict[str, Any]]:
        dialect_name = self.db.bind.dialect.name if self.db.bind else ""
        daily_runtime = {}
        daily_job_count = {}
        model_runtime = {}
        model_job_count = {}
        model_job_count_by_day = {}

        if dialect_name == "sqlite":
            jobs = (
                self.db.query(Job)
                .filter(
                    Job.team_id == team_id,
                    Job.start_time.isnot(None),
                    Job.end_time.isnot(None),
                    func.date(Job.start_time) >= start,
                    func.date(Job.start_time) <= end,
                )
                .all()
            )
            if not jobs:
                return []
            for job in jobs:
                day = job.start_time.date()
                runtime = (job.end_time - job.start_time).total_seconds()
                daily_runtime[day] = daily_runtime.get(day, 0.0) + runtime
                daily_job_count[day] = daily_job_count.get(day, 0) + 1
                model_runtime[(day, job.model_name)] = model_runtime.get((day, job.model_name), 0.0) + runtime
                model_job_count[job.model_name] = model_job_count.get(job.model_name, 0) + 1
                model_job_count_by_day[(day, job.model_name)] = model_job_count_by_day.get((day, job.model_name), 0) + 1
        else:
            runtime_expr = func.sum(func.extract("epoch", Job.end_time - Job.start_time))
            runtime_stmt = (
                select(
                    func.date(Job.start_time).label("day"),
                    Job.model_name,
                    func.count(Job.id).label("job_count"),
                    runtime_expr.label("runtime_seconds"),
                )
                .where(
                    Job.team_id == team_id,
                    Job.start_time.isnot(None),
                    Job.end_time.isnot(None),
                    func.date(Job.start_time) >= start,
                    func.date(Job.start_time) <= end,
                )
                .group_by(func.date(Job.start_time), Job.model_name)
            )
            runtime_rows = self.db.execute(runtime_stmt).all()
            if not runtime_rows:
                return []
            for day, model_name, job_count, runtime_seconds in runtime_rows:
                runtime = float(runtime_seconds or 0.0)
                daily_runtime[day] = daily_runtime.get(day, 0.0) + runtime
                daily_job_count[day] = daily_job_count.get(day, 0) + int(job_count)
                model_runtime[(day, model_name)] = model_runtime.get((day, model_name), 0.0) + runtime
                model_job_count[model_name] = model_job_count.get(model_name, 0) + int(job_count)
                model_job_count_by_day[(day, model_name)] = model_job_count_by_day.get((day, model_name), 0) + int(job_count)

        daily_cost_rows = self.db.execute(
            select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd))
            .where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
            .group_by(CostSnapshot.date)
        ).all()
        daily_costs = {row[0]: float(row[1] or 0.0) for row in daily_cost_rows}

        model_costs = {}
        for (day, model_name), runtime in model_runtime.items():
            daily_cost = daily_costs.get(day, 0.0)
            if daily_cost <= 0:
                continue
            total_runtime = daily_runtime.get(day, 0.0)
            if total_runtime > 0 and runtime > 0:
                share = runtime / total_runtime
            else:
                total_jobs = daily_job_count.get(day, 0)
                model_jobs = model_job_count_by_day.get((day, model_name), 0)
                share = (model_jobs / total_jobs) if total_jobs > 0 else 0.0
            model_costs[model_name] = model_costs.get(model_name, 0.0) + (daily_cost * share)

        results = [
            {
                "model_name": model_name,
                "total_cost_usd": round(model_costs.get(model_name, 0.0), 2),
                "job_count": model_job_count.get(model_name, 0),
            }
            for model_name in model_job_count.keys()
        ]
        results.sort(key=lambda item: item["total_cost_usd"], reverse=True)
        return results[:5]

    def _get_top_recommendations(self, team_id: UUID, start: date, end: date) -> list[dict[str, Any]]:
        filters = RecommendationFilters(start_date=start, end_date=end, team_id=team_id)
        recs = RecommendationEngine(self.db).generate_recommendations(filters)
        sorted_recs = sorted(recs.recommendations, key=lambda item: item.estimated_savings_usd, reverse=True)
        return [
            {
                "title": rec.title,
                "type": rec.type.value,
                "estimated_savings_usd": round(rec.estimated_savings_usd, 2),
            }
            for rec in sorted_recs[:5]
        ]
