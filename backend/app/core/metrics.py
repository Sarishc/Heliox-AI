"""Prometheus metrics for request latency, error rate, and throughput."""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Request count by method, path, status
REQUEST_COUNT = Counter(
    "heliox_http_requests_total",
    "Total HTTP requests",
    ["method", "path_template", "status_class"],
)

# Request latency histogram (seconds)
REQUEST_LATENCY = Histogram(
    "heliox_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path_template"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Error count (5xx)
ERROR_COUNT = Counter(
    "heliox_http_errors_total",
    "Total 5xx errors",
    ["method", "path_template"],
)


def get_status_class(status_code: int) -> str:
    """Return status class (2xx, 3xx, 4xx, 5xx)."""
    if status_code < 300:
        return "2xx"
    if status_code < 400:
        return "3xx"
    if status_code < 500:
        return "4xx"
    return "5xx"


def normalize_path(path: str) -> str:
    """Normalize path for metrics (collapse UUIDs, IDs)."""
    parts = path.split("/")
    normalized = []
    for p in parts:
        if not p:
            continue
        # Collapse UUIDs and numeric IDs
        if len(p) == 36 and p.count("-") == 4:
            normalized.append("{id}")
        elif p.isdigit():
            normalized.append("{id}")
        else:
            normalized.append(p)
    return "/" + "/".join(normalized) if normalized else path


def get_metrics() -> tuple[bytes, str]:
    """Return Prometheus metrics output."""
    return generate_latest(), CONTENT_TYPE_LATEST
