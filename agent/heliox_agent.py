#!/usr/bin/env python3
"""Heliox agent: collect GPU usage and send to Heliox."""
import argparse
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional

import requests


def collect_gpu_metrics_mock() -> List[Dict]:
    """Mock GPU metrics for local testing."""
    return [
        {"provider": "local", "gpu_type": "mock-gpu", "utilization": 50.0},
    ]


def collect_gpu_metrics_nvml() -> List[Dict]:
    """Collect GPU metrics using NVML if available."""
    try:
        import pynvml
    except Exception:
        return collect_gpu_metrics_mock()
    
    pynvml.nvmlInit()
    device_count = pynvml.nvmlDeviceGetCount()
    metrics = []
    for i in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle).decode("utf-8")
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        metrics.append({"provider": "local", "gpu_type": name, "utilization": float(util.gpu)})
    pynvml.nvmlShutdown()
    return metrics


PRICING_TABLE = {
    "a100": {"aws": 3.75, "gcp": 3.30, "azure": 3.60, "local": 3.50},
    "h100": {"aws": 4.90, "gcp": 4.50, "azure": 4.80, "local": 4.70},
    "v100": {"aws": 2.50, "gcp": 2.20, "azure": 2.40, "local": 2.30},
    "mock-gpu": {"local": 1.00},
}


def normalize_gpu_name(name: str) -> str:
    lowered = name.lower()
    if "a100" in lowered:
        return "a100"
    if "h100" in lowered:
        return "h100"
    if "v100" in lowered:
        return "v100"
    return lowered.replace(" ", "-")


def estimate_hourly_rate(gpu_type: str, provider: str) -> Optional[float]:
    pricing = PRICING_TABLE.get(gpu_type)
    if not pricing:
        return None
    return pricing.get(provider)


def build_usage_payload(metrics: List[Dict], interval_seconds: int, tags: Dict) -> Dict:
    now = datetime.now(timezone.utc).isoformat()
    payload = {"metrics": []}
    for m in metrics:
        gpu_type = normalize_gpu_name(m["gpu_type"])
        provider = m["provider"]
        gpu_hours = (m["utilization"] / 100.0) * (interval_seconds / 3600.0)
        payload["metrics"].append(
            {
                "timestamp": now,
                "provider": provider,
                "gpu_type": gpu_type,
                "gpu_hours": round(gpu_hours, 4),
                "tags": tags,
            }
        )
    return payload


def build_cost_payload(metrics: List[Dict], interval_seconds: int) -> Optional[Dict]:
    now_date = datetime.now(timezone.utc).date().isoformat()
    records = []
    for m in metrics:
        gpu_type = normalize_gpu_name(m["gpu_type"])
        provider = m["provider"]
        hourly_rate = estimate_hourly_rate(gpu_type, provider)
        if hourly_rate is None:
            continue
        gpu_hours = (m["utilization"] / 100.0) * (interval_seconds / 3600.0)
        cost_usd = round(hourly_rate * gpu_hours, 4)
        records.append(
            {
                "date": now_date,
                "provider": provider,
                "gpu_type": gpu_type,
                "cost_usd": cost_usd,
            }
        )
    if not records:
        return None
    return {"records": records}


def main():
    parser = argparse.ArgumentParser(description="Heliox GPU usage agent")
    parser.add_argument("--endpoint", required=True, help="Heliox API base URL, e.g. http://localhost:8000")
    parser.add_argument("--api-key", required=True, help="Team API key")
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds")
    parser.add_argument("--mock", action="store_true", help="Force mock mode")
    parser.add_argument("--send-costs", action="store_true", help="Send cost estimates", default=True)
    parser.add_argument("--tags", default="{}", help="JSON string of tags (cluster, env, project)")
    parser.add_argument("--environment", help="Environment tag (prod/staging/dev)")
    parser.add_argument("--project", help="Project tag (cost center identifier)")
    args = parser.parse_args()
    
    try:
        tags = json.loads(args.tags)
    except json.JSONDecodeError:
        tags = {}

    if args.environment:
        tags["environment"] = args.environment
    if args.project:
        tags["project"] = args.project
    
    while True:
        if args.mock:
            metrics = collect_gpu_metrics_mock()
        else:
            metrics = collect_gpu_metrics_nvml()
        
        payload = build_usage_payload(metrics, args.interval, tags)
        url = f"{args.endpoint.rstrip('/')}/api/v1/ingest/usage"
        headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code >= 400:
                print(f"[heliox-agent] Error {resp.status_code}: {resp.text}")
            else:
                print(f"[heliox-agent] Sent {len(payload['metrics'])} metrics")
        except Exception as exc:
            print(f"[heliox-agent] Failed to send metrics: {exc}")
        
        if args.send_costs:
            cost_payload = build_cost_payload(metrics, args.interval)
            if cost_payload:
                cost_url = f"{args.endpoint.rstrip('/')}/api/v1/ingest/cost"
                try:
                    resp = requests.post(cost_url, json=cost_payload, headers=headers, timeout=10)
                    if resp.status_code >= 400:
                        print(f"[heliox-agent] Cost error {resp.status_code}: {resp.text}")
                    else:
                        print(f"[heliox-agent] Sent {len(cost_payload['records'])} cost records")
                except Exception as exc:
                    print(f"[heliox-agent] Failed to send cost: {exc}")
        
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
