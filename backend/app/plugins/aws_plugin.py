"""Sample AWS cost/usage plugin (stub)."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from app.plugins.base import Plugin, CostRecord, UsageRecord
from app.plugins.registry import register_plugin


class AWSPlugin(Plugin):
    name = "aws"
    provider = "aws"
    
    def fetch_cost(self, *, start_date: date, end_date: date) -> Iterable[CostRecord]:
        # TODO: integrate with AWS Cost Explorer or CUR.
        return []
    
    def fetch_usage(self, *, start_date: date, end_date: date) -> Iterable[UsageRecord]:
        # TODO: integrate with CloudWatch or telemetry pipeline.
        return []


register_plugin(AWSPlugin)
