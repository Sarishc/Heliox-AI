# Custom Inference Integration

For serving frameworks that don't natively support OTel, use the Heliox simplified span format.

## Simplified Format

Send a `POST` request to `/api/v1/inference/spans` with up to 1,000 spans per batch.

### Request body

```json
{
  "spans": [
    {
      "model_name": "my-finetuned-llama",
      "model_version": "v2.1",
      "serving_framework": "custom",
      "cluster_name": "gpu-cluster-prod",
      "request_id": "req-abc123",
      "trace_id": "trace-xyz789",
      "started_at": "2026-04-20T14:00:00Z",
      "ended_at": "2026-04-20T14:00:01.234Z",
      "input_tokens": 512,
      "output_tokens": 256,
      "gpu_type": "A100",
      "gpu_count": 1
    }
  ]
}
```

### Field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_name` | string | Yes | Model identifier (e.g. `llama-3-70b`) |
| `started_at` | ISO 8601 datetime | Yes | Request start time (UTC) |
| `ended_at` | ISO 8601 datetime | Yes | Request end time (UTC) |
| `request_id` | string | Yes | Unique request ID |
| `model_version` | string | No | Model version tag |
| `serving_framework` | string | No | `vllm`, `tgi`, `triton`, `custom` |
| `cluster_name` | string | No | Must match `provider` in your cost integration |
| `trace_id` | string | No | Distributed trace ID for correlation |
| `input_tokens` | integer | No | Prompt token count |
| `output_tokens` | integer | No | Completion token count |
| `gpu_type` | string | No | GPU model (e.g. `A100`, `H100`) |
| `gpu_count` | integer | No | GPUs serving this request |

### Response

```json
{
  "accepted": 1,
  "rejected": 0,
  "errors": []
}
```

## Python Example

```python
import requests
from datetime import datetime, timezone, timedelta

HELIOX_API_KEY = "hx_your_api_key"
HELIOX_URL = "https://app.heliox.ai/api/v1/inference/spans"

def track_inference(model_name, started_at, ended_at, input_tokens=None, output_tokens=None):
    spans = [{
        "model_name": model_name,
        "request_id": f"req-{started_at.timestamp():.0f}",
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "serving_framework": "custom",
        "cluster_name": "my-gpu-cluster",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }]
    resp = requests.post(
        HELIOX_URL,
        json={"spans": spans},
        headers={"X-API-Key": HELIOX_API_KEY},
    )
    resp.raise_for_status()
    return resp.json()

# Usage
t0 = datetime.now(timezone.utc)
result = my_model.generate(prompt)
t1 = datetime.now(timezone.utc)

track_inference(
    model_name="my-finetuned-llama",
    started_at=t0,
    ended_at=t1,
    input_tokens=result.usage.prompt_tokens,
    output_tokens=result.usage.completion_tokens,
)
```

## OTLP Format

If your framework supports OTel, you can also send spans in OTLP JSON format.
The endpoint auto-detects the format based on the request body.

See [vllm.md](vllm.md) or [tgi.md](tgi.md) for OTel setup details.

## Cluster name matching

The `cluster_name` field must match the `provider` field in your connected cost integration
(e.g. the AWS account alias, GCP project name, or Azure subscription name). This is how
Heliox joins inference spans to GPU cost data for attribution.

```bash
# List your connected integrations to find provider names
heliox config list
```
