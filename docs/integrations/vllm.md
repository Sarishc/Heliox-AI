# vLLM Integration

Track per-request inference costs from vLLM using OpenTelemetry.

## Prerequisites

- vLLM ≥ 0.4.0
- `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` installed

## Setup (5 minutes)

### 1. Install the OTel exporter

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

### 2. Configure vLLM with OTel

Set these environment variables before starting your vLLM server:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://app.heliox.ai/api/v1/inference/spans"
export OTEL_EXPORTER_OTLP_HEADERS="X-API-Key=hx_your_api_key"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/json"
export OTEL_SERVICE_NAME="vllm-llama-3-70b"           # becomes cluster_name
export VLLM_CONFIGURE_LOGGING=1
```

Then start vLLM with tracing enabled:

```bash
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3-70b-Instruct \
  --enable-opentelemetry \
  --otlp-traces-endpoint "$OTEL_EXPORTER_OTLP_ENDPOINT"
```

### 3. Or use the Python SDK directly

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

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
tracer = trace.get_tracer("vllm")

# Instrument your inference calls
with tracer.start_as_current_span("llm_inference") as span:
    span.set_attribute("llm.model_name", "llama-3-70b")
    span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
    result = await llm.generate(prompt)
```

## Attribute Mapping

Heliox reads the following OTel span attributes:

| OTel Attribute | Heliox Field | Notes |
|----------------|--------------|-------|
| `llm.model_name` / `gen_ai.request.model` | `model_name` | |
| `llm.serving_framework` | `serving_framework` | Defaults to `vllm` |
| `llm.usage.prompt_tokens` / `gen_ai.usage.input_tokens` | `input_tokens` | |
| `llm.usage.completion_tokens` / `gen_ai.usage.output_tokens` | `output_tokens` | |
| `llm.cluster_name` | `cluster_name` | Joined to GPU cost data |
| `gen_ai.request.id` | `request_id` | |

## Self-hosted

If you're running a self-hosted Heliox instance, replace the endpoint:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="https://heliox.your-company.com/api/v1/inference/spans"
```

## Viewing Results

```bash
heliox inference models
heliox inference top --days 7
heliox inference summary --model llama-3-70b
```
