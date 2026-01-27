## Heliox Quickstart (15 minutes)

### Prerequisites
- Docker + Docker Compose
- `curl`

### 1) Start the stack
```
docker compose up -d --build
```

### 2) Run migrations
```
docker compose exec api alembic upgrade head
```

### 3) Create a user + get access token
```
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"founder@example.com","password":"password123","full_name":"Founder"}'

curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=founder@example.com&password=password123"
```
Copy the `access_token` from the login response.

### 4) Create team + first API key (welcome)
```
curl -s -X POST http://localhost:8000/api/v1/onboarding/welcome \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"team_name":"Acme AI","api_key_name":"Founder key","monthly_budget_usd":25000}'
```
Save:
- `team_id`
- `api_key` (shown only once)

Alternative (admin one-liner):
```
ADMIN_API_KEY=dev-admin-key-change-me TEAM_NAME="Acme AI" KEY_NAME="Founder key" \
  scripts/create-team-key.sh
```

### 5) Send mock usage data
```
curl -s -X POST http://localhost:8000/api/v1/ingest/usage \
  -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "metrics":[
      {"timestamp":"2026-01-01T00:00:00Z","provider":"aws","gpu_type":"a100","gpu_hours":1.5},
      {"timestamp":"2026-01-01T01:00:00Z","provider":"aws","gpu_type":"a100","gpu_hours":1.2}
    ]
  }'
```

### 6) (Optional) Run the agent in mock mode
```
python -m venv agent-venv
source agent-venv/bin/activate
pip install -r agent/requirements.txt
python agent/heliox_agent.py \
  --endpoint http://localhost:8000 \
  --api-key <API_KEY> \
  --interval 60 \
  --mock \
  --tags '{"env":"local","cluster":"dev"}'
```

### 7) Send mock cost data
```
curl -s -X POST http://localhost:8000/api/v1/ingest/cost \
  -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "records":[
      {"date":"2026-01-01","provider":"aws","gpu_type":"a100","cost_usd":1000},
      {"date":"2026-01-02","provider":"aws","gpu_type":"a100","cost_usd":1200}
    ]
  }'
```

### 8) Ingest KPI metrics (revenue/users/requests)
```
curl -s -X POST http://localhost:8000/api/v1/analytics/business-metrics \
  -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "metrics":[
      {"date":"2026-01-01","revenue_usd":5000,"active_users":200,"requests":12000},
      {"date":"2026-01-02","revenue_usd":5200,"active_users":210,"requests":13000}
    ]
  }'
```

### 9) Configure Slack webhook (team admin/owner)
```
curl -s -X POST http://localhost:8000/api/v1/alerts/webhook \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"team_id":"<TEAM_ID>","slack_webhook_url":"https://hooks.slack.com/services/..."}'
```

### 10) Create a budget policy
```
curl -s -X POST http://localhost:8000/api/v1/budgets \
  -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "environment":"prod",
    "project": null,
    "monthly_budget_usd": 25000,
    "alert_thresholds": [0.7, 0.85, 1.0],
    "is_enabled": true
  }'

curl -s http://localhost:8000/api/v1/budgets/status \
  -H "X-API-Key: <API_KEY>"
```

### 11) Verify analytics + forecast
```
curl -s "http://localhost:8000/api/v1/analytics/cost/by-team?start=2026-01-01&end=2026-01-02" \
  -H "X-API-Key: <API_KEY>"

curl -s "http://localhost:8000/api/v1/forecast/spend?provider=aws&gpu_type=a100&horizon_days=7" \
  -H "X-API-Key: <API_KEY>"

curl -s "http://localhost:8000/api/v1/analytics/business-efficiency?window_days=7" \
  -H "X-API-Key: <API_KEY>"
```

### 12) Open the dashboard
- Product UI: `http://localhost:3000`

### 13) Create your first board-ready report in 2 minutes
1. Navigate to `Reports` in the left nav.
2. Click **Save report** after choosing:
   - Date range
   - Sections (KPIs, daily spend, idle waste, top models, top recommendations)
3. Click **Export CSV** or **Export PDF** to download.
4. Click **Create share link** and copy the URL for a read-only view.

---

### Expected outputs
- `/ingest/usage` returns `status=success`
- `/ingest/cost` returns `status=success`
- Analytics/forecast endpoints return JSON data scoped to your team
