"""A provider-free adapter for the real Celery worker test, driven by the connection's stored configuration."""

import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.integrations.ledger.base import VERIFIED, Discovery, SourcePage, StreamSpec
from app.services.cost_ledger import normalize_line


class ConfiguredAdapter:
    provider = "aws"

    def __init__(self, config_encrypted):
        self.config = json.loads(config_encrypted)

    def streams(self):
        return [
            StreamSpec(
                provider="aws",
                scope_type="aws:linked_account",
                billing_account="",
                usage_account=self.config["account"],
                vantage="aws:caller:worker-test",
                metric="UnblendedCost",
                grouping_version="aws.v1.service+record_type",
                config={"metric": "UnblendedCost"},
            )
        ]

    def verify_scope(self):
        return {self.config["account"]: VERIFIED}

    def discover(self, window):
        return Discovery(supported=False)

    def fetch(self, spec, window):
        marker = self.config.get("hold_once")
        if marker and not Path(marker).exists():
            Path(marker).write_text("started")
            time.sleep(600)  # killed here by the test
        line = normalize_line(
            usage_date=date.fromisoformat(self.config["day"]),
            line_kind="aws:Usage",
            canonical_service="Amazon EC2",
            charge_class="usage",
            cost_bucket="worker",
            currency="USD",
            amount=Decimal(self.config["amount"]),
            dim_1="Amazon EC2",
        )
        yield SourcePage(0, (line,), is_last=True)
