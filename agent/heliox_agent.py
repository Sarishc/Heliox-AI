#!/usr/bin/env python3
"""Heliox agent: sample GPU utilization with NVML and report busy GPU-hours to Heliox.

Every ``--sample-seconds`` the agent reads each GPU's utilization. Every
``--interval`` seconds it sends, per GPU, to ``POST /api/v1/ingest/usage``:

- ``gpu_hours``: busy GPU-hours = average utilization x elapsed time
- ``allocated_gpu_hours``: elapsed time, since the GPU was present and powered

Heliox measures idle waste as cost x (1 - busy / allocated).

The API key is read from ``HELIOX_API_KEY`` or ``--api-key-file``, never from
the command line, so it doesn't show up in ``ps`` output or pod specs.
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

METADATA_TIMEOUT_SECONDS = 0.5

# Rough on-demand $/GPU-hour, used only with --send-costs. Real spend should come
# from a cloud billing connector; don't enable both or costs are counted twice.
PRICING_TABLE = {
    "a100": {"aws": 3.75, "gcp": 3.30, "azure": 3.60, "on-prem": 3.50},
    "h100": {"aws": 4.90, "gcp": 4.50, "azure": 4.80, "on-prem": 4.70},
    "v100": {"aws": 2.50, "gcp": 2.20, "azure": 2.40, "on-prem": 2.30},
    "mock-gpu": {"on-prem": 1.00},
}


class AgentError(Exception):
    """A configuration or environment problem the agent can't run past."""


# ── GPU readers ────────────────────────────────────────────────────────────────


def decode_gpu_name(raw) -> str:
    """pynvml returns bytes in older releases and str in current ones."""
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


def normalize_gpu_name(name: str) -> str:
    lowered = name.lower()
    for known in ("a100", "h100", "v100"):
        if known in lowered:
            return known
    return lowered.replace(" ", "-")


class NvmlReader:
    def __init__(self, pynvml):
        self._nvml = pynvml
        self._handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(pynvml.nvmlDeviceGetCount())]
        if not self._handles:
            raise AgentError("NVML found no GPUs on this node")
        self._types = [normalize_gpu_name(decode_gpu_name(pynvml.nvmlDeviceGetName(h))) for h in self._handles]

    def read(self) -> List[Dict]:
        return [
            {
                "index": i,
                "gpu_type": self._types[i],
                "utilization": float(self._nvml.nvmlDeviceGetUtilizationRates(h).gpu),
            }
            for i, h in enumerate(self._handles)
        ]


class MockReader:
    """Fake 50%-busy GPU for local testing. Used only when --mock is passed."""

    def read(self) -> List[Dict]:
        return [{"index": 0, "gpu_type": "mock-gpu", "utilization": 50.0}]


def open_reader(mock: bool):
    """Return a GPU reader. Without --mock, a missing or broken NVML is fatal."""
    if mock:
        return MockReader()
    try:
        import pynvml
    except ImportError as exc:
        raise AgentError("NVML library (pynvml) is not installed; install nvidia-ml-py or pass --mock") from exc
    try:
        pynvml.nvmlInit()
    except Exception as exc:
        raise AgentError(
            f"NVML failed to initialize ({exc}). Is the NVIDIA driver visible to this container? "
            "On Kubernetes, use the NVIDIA container runtime with NVIDIA_VISIBLE_DEVICES=all."
        ) from exc
    return NvmlReader(pynvml)


# ── Turning samples into busy GPU-hours ────────────────────────────────────────


class IntervalAccumulator:
    """Collects utilization samples per GPU and converts them to busy GPU-hours."""

    def __init__(self):
        self._samples: Dict[int, List[float]] = {}
        self._types: Dict[int, str] = {}

    def add(self, samples: List[Dict]) -> None:
        for s in samples:
            self._samples.setdefault(s["index"], []).append(s["utilization"])
            self._types[s["index"]] = s["gpu_type"]

    def flush(self, elapsed_seconds: float) -> List[Dict]:
        result = []
        for index, values in sorted(self._samples.items()):
            avg_utilization = sum(values) / len(values)
            busy_hours = (avg_utilization / 100.0) * (elapsed_seconds / 3600.0)
            # The GPU was present and powered for the whole interval: that's the paid capacity
            result.append(
                {
                    "gpu_type": self._types[index],
                    "gpu_hours": round(busy_hours, 6),
                    "allocated_gpu_hours": round(elapsed_seconds / 3600.0, 6),
                }
            )
        self._samples.clear()
        return result


def build_usage_payload(gpu_hours: List[Dict], provider: str, tags: Dict, now: datetime) -> Dict:
    return {
        "metrics": [
            {
                "timestamp": now.isoformat(),
                "provider": provider,
                "gpu_type": g["gpu_type"],
                "gpu_hours": g["gpu_hours"],
                "allocated_gpu_hours": g["allocated_gpu_hours"],
                "tags": tags,
            }
            for g in gpu_hours
        ]
    }


def build_cost_payload(gpu_hours: List[Dict], provider: str, now: datetime) -> Optional[Dict]:
    records = []
    for g in gpu_hours:
        hourly_rate = PRICING_TABLE.get(g["gpu_type"], {}).get(provider)
        # A powered GPU is billed whether busy or idle
        cost_usd = round((hourly_rate or 0) * g["allocated_gpu_hours"], 4)
        if cost_usd > 0:
            records.append(
                {"date": now.date().isoformat(), "provider": provider, "gpu_type": g["gpu_type"], "cost_usd": cost_usd}
            )
    return {"records": records} if records else None


# ── Configuration ──────────────────────────────────────────────────────────────


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    # allow_abbrev=False: otherwise the removed --api-key flag would silently match --api-key-file
    parser = argparse.ArgumentParser(description="Heliox GPU usage agent", allow_abbrev=False)
    parser.add_argument("--endpoint", required=True, help="Heliox API base URL, e.g. http://localhost:8000")
    parser.add_argument(
        "--api-key-file", help="File containing the team API key (default: read the HELIOX_API_KEY env var)"
    )
    parser.add_argument("--interval", type=int, default=60, help="Seconds between reports (default 60)")
    parser.add_argument("--sample-seconds", type=int, default=5, help="Seconds between GPU samples (default 5)")
    parser.add_argument(
        "--provider",
        choices=["aws", "gcp", "azure", "on-prem"],
        help="Cloud provider; auto-detected from instance metadata when omitted",
    )
    parser.add_argument("--mock", action="store_true", help="Report a fake GPU instead of reading NVML")
    parser.add_argument(
        "--send-costs",
        action="store_true",
        help="Also send cost estimates from a built-in price table. Leave off if a cloud billing "
        "integration is connected, or costs are counted twice.",
    )
    parser.add_argument("--tags", default="{}", help='JSON tags, e.g. \'{"cluster": "prod-us-east"}\'')
    parser.add_argument("--environment", help="Environment tag (prod/staging/dev)")
    parser.add_argument("--project", help="Project tag (cost center identifier)")
    return parser.parse_args(argv)


def load_api_key(env: Dict[str, str], api_key_file: Optional[str]) -> str:
    if api_key_file:
        with open(api_key_file) as f:
            key = f.read().strip()
    else:
        key = env.get("HELIOX_API_KEY", "").strip()
    if not key:
        raise AgentError("No API key: set HELIOX_API_KEY or pass --api-key-file")
    return key


def build_tags(args: argparse.Namespace, env: Dict[str, str]) -> Dict:
    try:
        tags = json.loads(args.tags)
    except json.JSONDecodeError as exc:
        raise AgentError(f"--tags is not valid JSON: {exc}") from exc
    if args.environment:
        tags["environment"] = args.environment
    if args.project:
        tags["project"] = args.project
    # Set from the downward API (spec.nodeName) in the Helm chart
    if env.get("NODE_NAME"):
        tags["node"] = env["NODE_NAME"]
    return tags


def detect_provider(http) -> str:
    """Identify the cloud from its instance-metadata service; 'on-prem' if none answers."""
    probes = [
        ("aws", "PUT", "http://169.254.169.254/latest/api/token", {"X-aws-ec2-metadata-token-ttl-seconds": "60"}),
        (
            "gcp",
            "GET",
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            {"Metadata-Flavor": "Google"},
        ),
        ("azure", "GET", "http://169.254.169.254/metadata/instance?api-version=2021-02-01", {"Metadata": "true"}),
    ]
    for provider, method, url, headers in probes:
        try:
            if http.request(method, url, headers=headers, timeout=METADATA_TIMEOUT_SECONDS).status_code == 200:
                return provider
        except Exception:
            continue
    return "on-prem"


def resolve_provider(args: argparse.Namespace, http) -> str:
    return args.provider or detect_provider(http)


# ── Main loop ──────────────────────────────────────────────────────────────────


def post(http, url: str, payload: Dict, headers: Dict, what: str) -> None:
    try:
        resp = http.request("POST", url, json=payload, headers=headers, timeout=10)
        if resp.status_code >= 400:
            print(f"[heliox-agent] {what} rejected: HTTP {resp.status_code}: {resp.text}", flush=True)
        else:
            print(f"[heliox-agent] Sent {what}", flush=True)
    except requests.RequestException as exc:
        print(f"[heliox-agent] Failed to send {what}: {exc}", flush=True)


def run(args: argparse.Namespace, env: Dict[str, str]) -> None:
    api_key = load_api_key(env, args.api_key_file)
    tags = build_tags(args, env)
    reader = open_reader(args.mock)
    http = requests.Session()
    provider = resolve_provider(args, http)
    base = args.endpoint.rstrip("/")
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    print(f"[heliox-agent] Reporting as provider={provider} every {args.interval}s", flush=True)

    acc = IntervalAccumulator()
    interval_start = time.monotonic()
    while True:
        acc.add(reader.read())
        time.sleep(args.sample_seconds)
        elapsed = time.monotonic() - interval_start
        if elapsed < args.interval:
            continue

        gpu_hours = acc.flush(elapsed_seconds=elapsed)
        interval_start = time.monotonic()
        now = datetime.now(timezone.utc)
        post(http, f"{base}/api/v1/ingest/usage", build_usage_payload(gpu_hours, provider, tags, now), headers, "usage")
        if args.send_costs:
            cost_payload = build_cost_payload(gpu_hours, provider, now)
            if cost_payload:
                post(http, f"{base}/api/v1/ingest/cost", cost_payload, headers, "cost estimates")


def install_signal_handlers() -> None:
    """Exit promptly on SIGTERM; as PID 1 in a container Python would otherwise ignore it."""

    def _exit(signum, frame):
        print("[heliox-agent] Received SIGTERM, exiting", flush=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _exit)


def main() -> None:
    install_signal_handlers()
    args = parse_args()
    try:
        run(args, dict(os.environ))
    except AgentError as exc:
        print(f"[heliox-agent] ERROR: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
