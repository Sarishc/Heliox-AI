# Text Generation Inference (TGI) Integration

Track per-request inference costs from Hugging Face TGI using OpenTelemetry.

## Prerequisites

- TGI ≥ 1.4.0 (native OTel support)
- `opentelemetry-exporter-otlp-proto-http` installed in your Python environment

## Setup

### 1. Configure TGI with OTel tracing

TGI exposes a `--otlp-endpoint` flag. Point it at Heliox:

```bash
docker run --gpus all \
  -e HUGGING_FACE_HUB_TOKEN=$HF_TOKEN \
  -e OTEL_EXPORTER_OTLP_HEADERS="X-API-Key=hx_your_api_key" \
  -p 8080:80 \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id meta-llama/Llama-3-70b-Instruct \
  --otlp-endpoint "https://app.heliox.ai/api/v1/inference/spans"
```

### 2. Kubernetes deployment

Add to your TGI container spec:

```yaml
env:
  - name: OTEL_EXPORTER_OTLP_HEADERS
    valueFrom:
      secretKeyRef:
        name: heliox-credentials
        key: api-key-header
  - name: OTEL_SERVICE_NAME
    value: "tgi-llama-70b"
args:
  - "--otlp-endpoint=https://app.heliox.ai/api/v1/inference/spans"
```

### 3. Manual instrumentation

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
import requests, time

provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint="https://app.heliox.ai/api/v1/inference/spans",
            headers={"X-API-Key": "hx_your_api_key"},
        )
    )
)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("tgi")

def generate(prompt: str, model: str = "llama-3-70b") -> str:
    with tracer.start_as_current_span("tgi_generate") as span:
        span.set_attribute("llm.model_name", model)
        span.set_attribute("llm.serving_framework", "tgi")
        t0 = time.monotonic()
        resp = requests.post(
            "http://localhost:8080/generate",
            json={"inputs": prompt, "parameters": {"max_new_tokens": 256}},
        )
        span.set_attribute("gen_ai.usage.output_tokens", resp.json().get("generated_tokens", 0))
        return resp.json()["generated_text"]
```

## Viewing Results

```bash
heliox inference models
heliox inference top --days 7
```
