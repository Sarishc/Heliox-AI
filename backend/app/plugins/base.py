"""Plugin interface for cost/telemetry adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional


@dataclass(frozen=True)
class CostRecord:
    date: date
    provider: str
    gpu_type: str
    cost_usd: float


@dataclass(frozen=True)
class UsageRecord:
    date: date
    provider: str
    gpu_type: str
    gpu_hours: float


class Plugin(ABC):
    """Base class for integration plugins."""
    
    name: str
    provider: str
    
    @abstractmethod
    def fetch_cost(self, *, start_date: date, end_date: date) -> Iterable[CostRecord]:
        """Fetch cost data for a date range."""
    
    @abstractmethod
    def fetch_usage(self, *, start_date: date, end_date: date) -> Iterable[UsageRecord]:
        """Fetch usage data for a date range."""
    
    def healthcheck(self) -> Optional[str]:
        """Optional connectivity check. Return error message if unhealthy."""
        return None
