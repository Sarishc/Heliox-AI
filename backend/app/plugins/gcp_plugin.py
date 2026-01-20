"""Sample GCP cost/usage plugin (stub)."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from app.plugins.base import Plugin, CostRecord, UsageRecord
from app.plugins.registry import register_plugin


class GCPPlugin(Plugin):
    name = "gcp"
    provider = "gcp"
    
    def fetch_cost(self, *, start_date: date, end_date: date) -> Iterable[CostRecord]:
        # TODO: integrate with GCP Billing export or BigQuery.
        return []
    
    def fetch_usage(self, *, start_date: date, end_date: date) -> Iterable[UsageRecord]:
        # TODO: integrate with GCP monitoring/telemetry.
        return []


register_plugin(GCPPlugin)
