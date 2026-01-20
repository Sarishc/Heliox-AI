## Heliox Agent

Collects GPU usage and posts to Heliox ingestion API.

### Install
```
pip install -r agent/requirements.txt
```

### Run (mock mode)
```
python agent/heliox_agent.py \
  --endpoint http://localhost:8000 \
  --api-key <API_KEY> \
  --interval 60 \
  --mock \
  --send-costs \
  --environment prod \
  --project core-inference
```

### Run (NVML mode)
```
python agent/heliox_agent.py \
  --endpoint https://api.heliox.ai \
  --api-key <API_KEY> \
  --interval 60 \
  --send-costs \
  --environment prod \
  --project core-inference
```
