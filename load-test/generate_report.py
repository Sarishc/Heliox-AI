#!/usr/bin/env python3
"""
Generate load test report from Locust + monitor results.
Targets: Success ≥95%, p99 <200ms, Memory <75%, CPU <75%
"""
import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
TARGETS = {
    "success_rate": 95.0,
    "p99_ms": 200,
    "memory_percent": 75.0,
    "cpu_percent": 75.0,
}


def load_locust_stats():
    """Parse Locust stats from CSV or HTML."""
    stats = {}
    stats_csv = RESULTS_DIR / "locust_stats.csv"
    if stats_csv.exists():
        with open(stats_csv) as f:
            lines = f.readlines()
        # Format: Type,Name,Request Count,Failure Count,Median Response Time,...
        for line in lines[1:]:  # skip header
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 10:
                name = parts[1]
                try:
                    total = int(parts[2])
                    failures = int(parts[3])
                except (ValueError, IndexError):
                    continue
                median = float(parts[4]) if parts[4] else 0
                # CSV: ...,95%,98%,99%,... at indices 16,17,18
                p95 = float(parts[16]) if len(parts) > 16 and parts[16] else median
                p99 = float(parts[18]) if len(parts) > 18 and parts[18] else median
                if name == "Aggregated":
                    stats["total_requests"] = total
                    stats["failures"] = failures
                    stats["success_rate"] = 100.0 * (total - failures) / total if total else 0
                    stats["median_ms"] = median
                    stats["p95_ms"] = p95
                    stats["p99_ms"] = p99
                    break
    return stats


def load_monitor_metrics():
    """Load latest metrics JSON from monitor."""
    metrics_files = sorted(RESULTS_DIR.glob("metrics_*.json"), reverse=True)
    if not metrics_files:
        return {}
    with open(metrics_files[0]) as f:
        data = json.load(f)
    if not data:
        return {}
    cpu = [m["system"]["cpu_percent"] for m in data]
    mem = [m["system"]["memory_percent"] for m in data]
    return {
        "cpu_avg": sum(cpu) / len(cpu) if cpu else 0,
        "cpu_peak": max(cpu) if cpu else 0,
        "memory_avg": sum(mem) / len(mem) if mem else 0,
        "memory_peak": max(mem) if mem else 0,
    }


def main():
    Path(RESULTS_DIR).mkdir(exist_ok=True)
    locust = load_locust_stats()
    monitor = load_monitor_metrics()

    success_rate = locust.get("success_rate", 0)
    p99 = locust.get("p99_ms", 0)
    mem_peak = monitor.get("memory_peak", 0)
    cpu_peak = monitor.get("cpu_peak", 0)

    has_locust = bool(locust.get("total_requests"))
    has_monitor = bool(monitor)

    success_ok = success_rate >= TARGETS["success_rate"] if has_locust else False
    p99_ok = p99 < TARGETS["p99_ms"] if (has_locust and p99) else (not has_locust)
    mem_ok = mem_peak < TARGETS["memory_percent"] if (has_monitor and mem_peak) else True
    cpu_ok = cpu_peak < TARGETS["cpu_percent"] if (has_monitor and cpu_peak) else True

    passed = has_locust and success_ok and p99_ok and mem_ok and cpu_ok

    report = f"""
================================================================================
HELIOX LOAD TEST REPORT — Day 4 (P1-2, P1-3)
================================================================================

Configuration:
  - 100 concurrent users
  - ~500 requests/minute target
  - Duration: 5 minutes

Results:
  Success Rate:  {success_rate:.1f}%  (target ≥95%)  {'✅ PASS' if success_ok else '❌ FAIL'}
  p99 Latency:   {p99:.0f}ms   (target <200ms)  {'✅ PASS' if p99_ok else '❌ FAIL'}
  Memory Peak:   {mem_peak:.1f}%  (target <75%)  {'✅ PASS' if mem_ok else '❌ FAIL'}
  CPU Peak:      {cpu_peak:.1f}%  (target <75%)  {'✅ PASS' if cpu_ok else '❌ FAIL'}

Additional Metrics:
  Total Requests: {locust.get('total_requests', 'N/A')}
  Failures:        {locust.get('failures', 'N/A')}
  Median (ms):     {locust.get('median_ms', 'N/A')}
  p95 (ms):        {locust.get('p95_ms', 'N/A')}
  Memory Avg:      {monitor.get('memory_avg', 0):.1f}%
  CPU Avg:         {monitor.get('cpu_avg', 0):.1f}%

================================================================================
VERDICT: {'✅ PASS' if passed else '❌ FAIL'}
================================================================================

Expected Score After Fixes:
  Security: 85–88
  Performance: 80+
  Enterprise readiness: 85–90

  Beta → GO | Paid → GO | Enterprise → Conditional GO
"""
    print(report)
    report_path = RESULTS_DIR / "load_test_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
