"""Minimal Heliox SDK helper."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict

import requests


def send_usage(
    *,
    endpoint: str,
    api_key: str,
    metrics: List[Dict],
    timeout: int = 10
) -> dict:
    url = f"{endpoint.rstrip('/')}/api/v1/ingest/usage"
    payload = {"metrics": metrics}
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def build_metric(
    provider: str,
    gpu_type: str,
    gpu_hours: float,
    tags: dict | None = None,
    allocated_gpu_hours: float | None = None,
) -> Dict:
    """gpu_hours is busy time; pass allocated_gpu_hours (powered time) to get idle-waste numbers."""
    metric = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "gpu_type": gpu_type,
        "gpu_hours": float(Decimal(gpu_hours)),
        "tags": tags or {},
    }
    if allocated_gpu_hours is not None:
        metric["allocated_gpu_hours"] = float(Decimal(allocated_gpu_hours))
    return metric
