# Heliox Observability & Monitoring

Phase 5 — Production reliability: tracing, metrics, logging, alerting.

## Overview

| Component | Purpose |
|-----------|---------|
| **OpenTelemetry** | Distributed tracing (when OTEL_ENABLED=true) |
| **Prometheus** | Request latency, error rate, throughput metrics |
| **Sentry** | Error monitoring and crash reporting |
| **Structured Logging** | JSON logs with correlation_id |
| **CloudWatch Alarms** | 5xx, CPU > 80%, Memory > 80% |

## Health Endpoints

| Endpoint | Purpose | K8s Probe |
|----------|---------|-----------|
| `GET /health` | Liveness — process is running | livenessProbe |
| `GET /liveness` | Same as /health | livenessProbe |
| `GET /ready` | Readiness — DB + Redis connected | readinessProbe |
| `GET /readiness` | Alias for /ready | readinessProbe |
| `GET /health/db` | Database-only health | — |
| `GET /metrics` | Prometheus metrics | — |

## Prometheus Metrics

```
heliox_http_requests_total{method, path_template, status_class}
heliox_http_request_duration_seconds{method, path_template}
heliox_http_errors_total{method, path_template}  # 5xx only
heliox_http_requests_in_flight{method, path_template}  # gauge
```

**Excluded paths** (not recorded, to avoid probe noise): `/health`, `/health/db`, `/liveness`, `/readiness`, `/ready`, `/metrics`, `/`

**Path normalization:** UUIDs → `{id}`, numeric IDs → `{id}`, long tokens → `{token}` (low cardinality)

**Scrape config:**
```yaml
scrape_configs:
  - job_name: 'heliox-api'
    metrics_path: /metrics
    static_configs:
      - targets: ['api:8000']
```

## Correlation IDs

Every request gets a correlation ID from:
1. `X-Correlation-ID` header (preferred)
2. `X-Request-ID` header
3. Auto-generated UUID

Response headers include:
- `X-Request-ID`
- `X-Correlation-ID`
- `X-Response-Time-Ms`

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `SENTRY_DSN` | — | Sentry DSN (empty = disabled) |
| `SENTRY_ENVIRONMENT` | ENV | Sentry environment |
| `SENTRY_RELEASE` | — | Release version (git SHA, semver). Enables release tracking. |
| `OTEL_ENABLED` | false | Enable OpenTelemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://localhost:4317 | OTLP endpoint |
| `LOG_JSON_FORMAT` | true | Structured JSON logs |

## Sentry Safety

- **Disabled in test:** Sentry does not initialize when `ENV=test`
- **Scrubbing:** `before_send` filters Authorization, X-API-Key, Cookie, and similar headers
- **Request bodies:** `max_request_body_size="never"` to avoid sending request payloads
- **Correlation IDs:** `request_id` and `correlation_id` attached as tags when capturing exceptions
- **Celery:** Sentry initializes in workers via `worker_init` signal; task failures are captured

## CloudWatch Alarms (Terraform)

Alarms are created in the ECS module:

- **heliox-{env}-api-cpu-high** — CPU > 80% for 2 periods
- **heliox-{env}-api-memory-high** — Memory > 80% for 2 periods
- **heliox-{env}-alb-5xx-errors** — 5xx count > 5 in 5 min

Set `alarm_sns_topic_arn` in terraform.tfvars for notifications.

## No Silent Failures

- **Sentry** captures unhandled exceptions
- **Prometheus** tracks 5xx via `heliox_http_errors_total`
- **CloudWatch** alarms fire on elevated error rate
- **Structured logs** include correlation_id for traceability
