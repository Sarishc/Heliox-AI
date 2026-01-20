"""Sample on-prem cost/usage plugin (stub)."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from app.plugins.base import Plugin, CostRecord, UsageRecord
from app.plugins.registry import register_plugin


class OnPremPlugin(Plugin):
    name = "onprem"
    provider = "onprem"
    
    def fetch_cost(self, *, start_date: date, end_date: date) -> Iterable[CostRecord]:
        # TODO: integrate with on-prem billing or chargeback system.
        return []
    
    def fetch_usage(self, *, start_date: date, end_date: date) -> Iterable[UsageRecord]:
        # TODO: integrate with on-prem telemetry stack.
        return []


register_plugin(OnPremPlugin)
