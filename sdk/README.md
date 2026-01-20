## Heliox SDK (Python)

Minimal helper to send usage metrics.

### Install
```
pip install -r sdk/requirements.txt
```

### Example
```python
from sdk.heliox_sdk import send_usage, build_metric

metrics = [
    build_metric(provider="aws", gpu_type="a100", gpu_hours=1.5, tags={"env":"prod"})
]
send_usage(endpoint="https://api.heliox.ai", api_key="YOUR_API_KEY", metrics=metrics)
```
