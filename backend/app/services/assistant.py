"""LLM-style assistant query routing (deterministic, tool-limited)."""
from __future__ import annotations

import json
import hashlib
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot
from app.models.job import Job
from app.services.forecasting import ForecastingService, DEFAULT_HORIZON_DAYS, MAX_HORIZON_DAYS
from app.core.cache import get_redis
from app.services.optimizer import SelfOptimizingAdvisor


@dataclass(frozen=True)
class RoutedAction:
    tool: str
    params: Dict[str, Any]


class AssistantQueryService:
    """
    Deterministic router that maps questions to a limited set of tools.
    Safe by design: no arbitrary execution, only whitelisted tools.
    """
    
    CACHE_TTL_SECONDS = 600
    
    def __init__(self, db: Session):
        self.db = db
    
    def handle(self, *, team_id: UUID, question: str) -> Dict[str, Any]:
        routed = self._route(question, team_id)
        if routed.tool == "analytics_cost_by_model":
            redis_client = get_redis()
            cache_key = self._cache_key(team_id, routed.tool, routed.params)
            cached = self._get_cached(redis_client, cache_key)
            if cached is not None:
                data = cached
                return {
                    "tool_used": routed.tool,
                    "answer": "Here is cost by model for the requested period.",
                    "data": {"items": data},
                    "tool_trace": {
                        "tool": routed.tool,
                        "params": routed.params,
                        "status": "ok",
                        "duration_ms": 0.0,
                        "row_count": len(data),
                        "query_count": 0,
                        "cache_hit": True,
                    },
                    "fallback": False,
                }
            start = time.perf_counter()
            data, query_count = self._cost_by_model(
                team_id, routed.params["start_date"], routed.params["end_date"]
            )
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._set_cached(redis_client, cache_key, data)
            return {
                "tool_used": routed.tool,
                "answer": "Here is cost by model for the requested period.",
                "data": {"items": data},
                "tool_trace": {
                    "tool": routed.tool,
                    "params": routed.params,
                    "status": "ok",
                    "duration_ms": duration_ms,
                    "row_count": len(data),
                    "query_count": query_count,
                    "cache_hit": False,
                },
                "fallback": False,
            }
        if routed.tool == "analytics_cost_by_team":
            redis_client = get_redis()
            cache_key = self._cache_key(team_id, routed.tool, routed.params)
            cached = self._get_cached(redis_client, cache_key)
            if cached is not None:
                data = cached
                return {
                    "tool_used": routed.tool,
                    "answer": "Here is cost by team for the requested period.",
                    "data": {"items": data},
                    "tool_trace": {
                        "tool": routed.tool,
                        "params": routed.params,
                        "status": "ok",
                        "duration_ms": 0.0,
                        "row_count": len(data),
                        "query_count": 0,
                        "cache_hit": True,
                    },
                    "fallback": False,
                }
            start = time.perf_counter()
            data, query_count = self._cost_by_team(
                team_id, routed.params["start_date"], routed.params["end_date"]
            )
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._set_cached(redis_client, cache_key, data)
            return {
                "tool_used": routed.tool,
                "answer": "Here is cost by team for the requested period.",
                "data": {"items": data},
                "tool_trace": {
                    "tool": routed.tool,
                    "params": routed.params,
                    "status": "ok",
                    "duration_ms": duration_ms,
                    "row_count": len(data),
                    "query_count": query_count,
                    "cache_hit": False,
                },
                "fallback": False,
            }
        if routed.tool == "forecast_spend":
            redis_client = get_redis()
            forecast_service = ForecastingService(self.db, redis_client)
            start = time.perf_counter()
            cache_key = forecast_service._generate_cache_key(
                forecast_type="spend",
                team_id=team_id,
                provider=routed.params.get("provider"),
                gpu_type=routed.params.get("gpu_type"),
                horizon_days=routed.params["horizon_days"],
            )
            cached = forecast_service._get_cached_forecast(cache_key)
            cache_hit = cached is not None
            data = cached or forecast_service.forecast_spend(
                team_id=team_id,
                provider=routed.params.get("provider"),
                gpu_type=routed.params.get("gpu_type"),
                horizon_days=routed.params["horizon_days"],
            )
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            row_count = len(data.get("forecast", [])) if isinstance(data, dict) else None
            return {
                "tool_used": routed.tool,
                "answer": "Here is the spend forecast.",
                "data": data,
                "tool_trace": {
                    "tool": routed.tool,
                    "params": routed.params,
                    "status": "ok",
                    "duration_ms": duration_ms,
                    "row_count": row_count,
                    "query_count": None,
                    "cache_hit": cache_hit,
                },
                "fallback": False,
            }
        if routed.tool == "forecast_usage":
            redis_client = get_redis()
            forecast_service = ForecastingService(self.db, redis_client)
            start = time.perf_counter()
            cache_key = forecast_service._generate_cache_key(
                forecast_type="usage",
                team_id=team_id,
                provider=routed.params.get("provider"),
                gpu_type=routed.params.get("gpu_type"),
                horizon_days=routed.params["horizon_days"],
            )
            cached = forecast_service._get_cached_forecast(cache_key)
            cache_hit = cached is not None
            data = cached or forecast_service.forecast_usage(
                team_id=team_id,
                provider=routed.params.get("provider"),
                gpu_type=routed.params.get("gpu_type"),
                horizon_days=routed.params["horizon_days"],
            )
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            row_count = len(data.get("forecast", [])) if isinstance(data, dict) else None
            return {
                "tool_used": routed.tool,
                "answer": "Here is the usage forecast.",
                "data": data,
                "tool_trace": {
                    "tool": routed.tool,
                    "params": routed.params,
                    "status": "ok",
                    "duration_ms": duration_ms,
                    "row_count": row_count,
                    "query_count": None,
                    "cache_hit": cache_hit,
                },
                "fallback": False,
            }
        if routed.tool == "optimizer_recommendations":
            advisor = SelfOptimizingAdvisor(self.db)
            redis_client = get_redis()
            cache_key = self._cache_key(team_id, routed.tool, routed.params)
            cached = self._get_cached(redis_client, cache_key)
            if cached is not None:
                data = cached
                return {
                    "tool_used": routed.tool,
                    "answer": "Here are optimization recommendations based on recent usage.",
                    "data": {"recommendations": data},
                    "tool_trace": {
                        "tool": routed.tool,
                        "params": routed.params,
                        "status": "ok",
                        "duration_ms": 0.0,
                        "row_count": len(data),
                        "query_count": 0,
                        "cache_hit": True,
                    },
                    "fallback": False,
                }
            start = time.perf_counter()
            data = advisor.generate(
                team_id=team_id,
                start_date=routed.params["start_date"],
                end_date=routed.params["end_date"],
            )
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._set_cached(redis_client, cache_key, data)
            return {
                "tool_used": routed.tool,
                "answer": "Here are optimization recommendations based on recent usage.",
                "data": {"recommendations": data},
                "tool_trace": {
                    "tool": routed.tool,
                    "params": routed.params,
                    "status": "ok",
                    "duration_ms": duration_ms,
                    "row_count": len(data),
                    "query_count": None,
                    "cache_hit": False,
                },
                "fallback": False,
            }
        
        return {
            "tool_used": "fallback",
            "answer": (
                "I can answer questions about cost by model, cost by team, "
                "spend forecasts, usage forecasts, or optimization recommendations."
            ),
            "data": {"supported_tools": self._supported_tools()},
            "tool_trace": {
                "tool": "fallback",
                "params": {},
                "status": "unsupported",
                "duration_ms": 0.0,
                "row_count": 0,
                "query_count": 0,
                "cache_hit": None,
            },
            "fallback": True,
        }
    
    def _route(self, question: str, team_id: UUID) -> RoutedAction:
        normalized = question.strip().lower()
        start_date, end_date = self._parse_date_range(normalized, team_id)
        horizon_days = self._parse_horizon_days(normalized)
        
        if any(token in normalized for token in ["recommend", "optimize", "savings", "idle", "roi"]):
            return RoutedAction(
                tool="optimizer_recommendations",
                params={"start_date": start_date, "end_date": end_date},
            )
        
        if any(token in normalized for token in ["forecast", "predict", "projection", "next"]):
            if any(token in normalized for token in ["usage", "utilization", "gpu hours"]):
                return RoutedAction(
                    tool="forecast_usage",
                    params={"horizon_days": horizon_days},
                )
            return RoutedAction(
                tool="forecast_spend",
                params={"horizon_days": horizon_days},
            )
        
        if "by model" in normalized or ("model" in normalized and "cost" in normalized):
            return RoutedAction(
                tool="analytics_cost_by_model",
                params={"start_date": start_date, "end_date": end_date},
            )
        
        if "by team" in normalized or ("team" in normalized and "cost" in normalized):
            return RoutedAction(
                tool="analytics_cost_by_team",
                params={"start_date": start_date, "end_date": end_date},
            )
        
        return RoutedAction(tool="fallback", params={})
    
    def _parse_date_range(self, question: str, team_id: UUID) -> tuple[date, date]:
        days = self._parse_recent_days(question) or 14
        end_date = self._latest_cost_date(team_id) or date.today()
        start_date = end_date - timedelta(days=days)
        return start_date, end_date

    def _latest_cost_date(self, team_id: UUID) -> Optional[date]:
        row = self.db.execute(
            select(func.max(CostSnapshot.date)).where(CostSnapshot.team_id == team_id)
        ).scalar_one_or_none()
        return row if row else None
    
    @staticmethod
    def _parse_recent_days(question: str) -> Optional[int]:
        match = re.search(r"last\s+(\d+)\s+days", question)
        if match:
            return max(1, min(90, int(match.group(1))))
        if "last week" in question or "past week" in question:
            return 7
        if "last month" in question or "past month" in question:
            return 30
        return None
    
    @staticmethod
    def _parse_horizon_days(question: str) -> int:
        match = re.search(r"next\s+(\d+)\s+days", question)
        if match:
            return max(1, min(MAX_HORIZON_DAYS, int(match.group(1))))
        return DEFAULT_HORIZON_DAYS
    
    def _cost_by_model(self, team_id: UUID, start: date, end: date) -> tuple[list[dict], int]:
        query_count = 0
        stmt = (
            select(
                Job.model_name,
                func.count(Job.id).label("job_count")
            )
            .where(
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end,
                Job.team_id == team_id,
            )
            .group_by(Job.model_name)
        )
        rows = self.db.execute(stmt).all()
        query_count += 1
        items = []
        for model_name, job_count in rows:
            gpu_stmt = (
                select(Job.gpu_type, Job.provider)
                .where(
                    Job.model_name == model_name,
                    Job.team_id == team_id,
                    func.date(Job.start_time) >= start,
                    func.date(Job.start_time) <= end,
                )
                .distinct()
            )
            gpu_rows = self.db.execute(gpu_stmt).all()
            query_count += 1
            total_cost = 0.0
            for gpu_type, provider in gpu_rows:
                cost_stmt = (
                    select(func.sum(CostSnapshot.cost_usd))
                    .where(
                        CostSnapshot.team_id == team_id,
                        CostSnapshot.date >= start,
                        CostSnapshot.date <= end,
                        CostSnapshot.gpu_type == gpu_type.lower(),
                        CostSnapshot.provider == provider.lower(),
                    )
                )
                gpu_cost = self.db.execute(cost_stmt).scalar_one_or_none() or 0.0
                query_count += 1
                total_cost += float(gpu_cost)
            items.append(
                {
                    "model_name": model_name,
                    "total_cost_usd": round(total_cost, 2),
                    "job_count": job_count,
                    "start_date": str(start),
                    "end_date": str(end),
                }
            )
        items.sort(key=lambda x: x["total_cost_usd"], reverse=True)
        return items, query_count
    
    def _cost_by_team(self, team_id: UUID, start: date, end: date) -> tuple[list[dict], int]:
        query_count = 0
        stmt = (
            select(
                Job.team_id,
                func.count(Job.id).label("job_count")
            )
            .where(
                func.date(Job.start_time) >= start,
                func.date(Job.start_time) <= end,
                Job.team_id == team_id,
            )
            .group_by(Job.team_id)
        )
        rows = self.db.execute(stmt).all()
        query_count += 1
        items = []
        for team_id_value, job_count in rows:
            cost_stmt = (
                select(func.sum(CostSnapshot.cost_usd))
                .where(
                    CostSnapshot.team_id == team_id_value,
                    CostSnapshot.date >= start,
                    CostSnapshot.date <= end,
                )
            )
            total_cost = self.db.execute(cost_stmt).scalar_one_or_none() or 0.0
            query_count += 1
            items.append(
                {
                    "team_id": str(team_id_value),
                    "total_cost_usd": round(float(total_cost), 2),
                    "job_count": job_count,
                    "start_date": str(start),
                    "end_date": str(end),
                }
            )
        return items, query_count
    
    @staticmethod
    def _supported_tools() -> list[str]:
        return [
            "analytics_cost_by_model",
            "analytics_cost_by_team",
            "forecast_spend",
            "forecast_usage",
            "optimizer_recommendations",
        ]

    def _cache_key(self, team_id: UUID, tool: str, params: Dict[str, Any]) -> str:
        normalized = json.dumps(
            {"team_id": str(team_id), "tool": tool, "params": params},
            default=str,
            sort_keys=True
        )
        return f"assistant:{hashlib.md5(normalized.encode()).hexdigest()}"

    def _get_cached(self, redis_client, cache_key: str) -> Optional[list]:
        if not redis_client:
            return None
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            return None
        return None

    def _set_cached(self, redis_client, cache_key: str, data: list) -> None:
        if not redis_client:
            return
        try:
            redis_client.setex(cache_key, self.CACHE_TTL_SECONDS, json.dumps(data, default=str))
        except Exception:
            return
