## Heliox Agent

Samples each GPU's utilization with NVML and reports, per GPU, to
`POST /api/v1/ingest/usage`:

- **busy GPU-hours** (average utilization × elapsed time), and
- **allocated GPU-hours** (elapsed time: the GPU was present and powered).

Heliox measures idle waste as cost × (1 − busy ÷ allocated).

- The API key comes from `HELIOX_API_KEY` or `--api-key-file`. It is never a
  command-line flag, so it doesn't show up in `ps` or pod specs. An
  ingest-only key is enough.
- If NVML isn't available, the agent exits with an error. It sends fake data
  only when you pass `--mock`.
- The cloud provider (`aws` / `gcp` / `azure` / `on-prem`) is detected from
  instance metadata. Override it with `--provider`.
- `--send-costs` (off by default) also posts cost *estimates* from a built-in
  price table. Leave it off if a cloud billing integration is connected, or
  costs are counted twice.

### Kubernetes (recommended)

Install with the Helm chart (`charts/heliox`, `agent.*` values) or run
`heliox agent deploy`. Both run the `ghcr.io/sarishc/heliox-agent` image, which
CI publishes from `agent/Dockerfile` on every push to `main`.

GPU nodes need the NVIDIA container runtime. If it isn't the default runtime,
set `agent.runtimeClassName=nvidia`.

### Run locally (mock mode)
```
pip install -r agent/requirements.txt
HELIOX_API_KEY=<API_KEY> python agent/heliox_agent.py \
  --endpoint http://localhost:8000 \
  --interval 60 \
  --mock \
  --environment dev \
  --project core-inference
```

### Run on a GPU host
```
HELIOX_API_KEY=<API_KEY> python agent/heliox_agent.py \
  --endpoint https://api.example.com \
  --environment prod \
  --project core-inference
```

### Tests
```
pip install -r agent/requirements.txt pytest
python -m pytest agent/tests
```
