# Heliox — GPU cost visibility for ML teams

Heliox tracks, analyzes, and optimizes GPU infrastructure costs across
AWS, GCP, and Azure. Think Kubecost, but built specifically for ML workloads.

- Real-time GPU utilization and cost per job, per model, per team
- Anomaly detection and budget guardrails with Slack alerts
- Cost forecasting using your actual workload patterns
- One-line agent deploy via Kubernetes DaemonSet
- Multi-cloud: AWS Cost Explorer, GCP BigQuery Billing, Azure Cost Management

## Tech Stack

- **Backend**: FastAPI (Python 3.11), PostgreSQL 15, Redis 7, SQLAlchemy 2.0, Alembic
- **Frontend**: Next.js (apps/app/)
- **Infrastructure**: AWS ECS Fargate, ElastiCache, Terraform

## Project Structure

```
heliox/
├── apps/
│   └── app/                    # Product frontend (Next.js)
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI application entry point
│   │   ├── api/routes/         # All API route handlers (36 modules)
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── crud/               # Database access layer
│   │   ├── auth/               # Authentication, RBAC, brute-force protection
│   │   ├── core/               # Config, DB, Redis, rate limiting
│   │   ├── integrations/       # AWS, GCP, Azure cost provider integrations
│   │   └── services/           # Business logic (email, reports, forecasting)
│   ├── alembic/                # Database migrations
│   ├── tests/                  # Test suite
│   └── Dockerfile
├── agent/                      # Kubernetes DaemonSet cost agent (NVML)
├── terraform/                  # AWS infrastructure (ECS, RDS, ElastiCache, ALB)
└── docker-compose.yml
```

## Quick Start

```bash
# Start all services
docker-compose up -d

# Apply DB migrations
docker-compose exec api alembic upgrade head

# API docs
open http://localhost:8000/docs
```

For the full 15-minute founder onboarding flow, see `docs/QUICKSTART.md`.

## How Heliox Calculates Cost

Heliox computes spend and efficiency metrics from three sources:

- **Cost snapshots** (`cost_snapshots`): daily provider/GPU costs ingested from AWS Cost Explorer, GCP BigQuery Billing, or Azure Cost Management.
- **Usage snapshots** (`usage_snapshots`): GPU hours and utilization from the DaemonSet agent or manual ingest.
- **Job metadata** (`jobs`): optional per-job attribution for model name, team, environment.

Key formulas:
- **Total spend**: `sum(cost_usd)` across the selected date window.
- **Idle waste**: `sum(cost_usd * idle_ratio)` where `idle_ratio = max(0, (expected_hours - usage_hours) / expected_hours)`.
- **Cost per model**: join `jobs` → `cost_snapshots` on `(provider, gpu_type, date)`.

Each major endpoint supports `?include_explain=true` to return the formula, inputs, assumptions, and confidence level alongside the result.

## Running Locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Requires Postgres + Redis (fastest via Docker):
docker-compose up -d postgres redis

export DATABASE_URL="postgresql+psycopg2://heliox:heliox_password@localhost:5432/heliox_db"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="dev-secret-key-change-in-production"

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Database Migrations

```bash
# Create a migration from model changes
alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

## Testing

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

## Configuration

See [`backend/.env.example`](backend/.env.example) for all environment variables.
`REDIS_URL` and `DATABASE_URL` are required — no defaults. The app will refuse to start without them.

## Security

- Redis required for rate limiting, brute-force protection, and JWT blacklisting — no silent fallbacks
- httpOnly cookie auth with token blacklisting on logout
- RBAC (owner / admin / member) enforced at route level
- All integration credentials encrypted at rest (AES-256-GCM)

## Deployment

Infrastructure is in `terraform/`. The stack deploys to AWS: ECS Fargate + RDS PostgreSQL + ElastiCache Redis + ALB + Route53.

```bash
cd terraform
terraform init
terraform apply
```

## License

MIT
