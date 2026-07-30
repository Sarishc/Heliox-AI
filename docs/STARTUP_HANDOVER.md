# Heliox AI Startup Handover

This guide is for a startup adopting Heliox AI without Docker. PostgreSQL and
Redis may run locally as native services or be supplied by managed providers.

## What the adopter receives

- Multi-tenant web application and REST API
- Email/password authentication, Google OAuth, SAML, RBAC, and API keys
- AWS, GCP, and Azure cost ingestion
- Forecasts, anomaly detection, budgets, reports, and recommendations
- Stripe subscription and usage-metering integration
- Celery workers and scheduled jobs
- Database migrations, automated backend tests, frontend build checks, and
  browser end-to-end tests

Each adopting company must supply its own domain, cloud account, database,
Redis, email sender, billing account, OAuth/SAML credentials, monitoring, and
legal policies. Secrets and customer data are intentionally not included.

## Native local setup (macOS)

Prerequisites: Python 3.11, Node 20+, pnpm 9, PostgreSQL 16+, and Redis 7+.

```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis

createdb heliox
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pnpm install --frozen-lockfile
```

Copy `backend/.env.example` to `backend/.env`, then set at minimum:

```dotenv
ENV=dev
SECRET_KEY=<openssl-rand-hex-32>
DATABASE_URL=postgresql+psycopg2://localhost:5432/heliox
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=["http://localhost:3000"]
FRONTEND_URL=http://localhost:3000
API_BASE_URL=http://localhost:8000
```

Apply migrations and start each process in its own terminal:

```bash
cd backend
source ../.venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
cd backend
source ../.venv/bin/activate
celery -A app.celery_app.celery_app worker --loglevel=INFO
```

```bash
cd backend
source ../.venv/bin/activate
celery -A app.celery_app.celery_app beat --loglevel=INFO
```

```bash
pnpm --filter app dev
```

Verify:

```bash
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:8000/docs
curl --fail http://localhost:3000
```

## Production deployment contract

Use managed PostgreSQL with encryption, automated backups, point-in-time
recovery, and tested restores. Use managed Redis with TLS and authentication.
Run the API, worker, beat scheduler, and frontend as independently restartable
services behind TLS. Run `alembic upgrade head` once as a release task before
shifting traffic.

Required production configuration:

- `ENV=production`
- Strong, secret-manager-backed `SECRET_KEY`, `ADMIN_API_KEY`, and
  `INTEGRATIONS_ENCRYPTION_KEY`
- TLS `DATABASE_URL` and `REDIS_URL`
- Exact `CORS_ORIGINS`, `FRONTEND_URL`, and `API_BASE_URL` for the company domain
- `RESEND_API_KEY` and a verified `EMAIL_FROM` domain
- Stripe secret, webhook secret, price IDs, and meter event names when billing
  customers
- Google OAuth and/or SAML credentials when those login methods are offered
- `SENTRY_DSN`, centralized logs, uptime checks, and paging ownership

Do not reuse development secrets, demo users, databases, webhook secrets, or
OAuth applications between companies.

## Release verification

Run these gates from a clean checkout:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
PYTHONPATH=. pytest
alembic upgrade head
cd ..

pnpm install --frozen-lockfile
pnpm audit --prod
pnpm --filter app build
pnpm --filter app test:e2e
```

Then verify a production-like environment:

1. Register, verify email, log in, log out, reset password.
2. Create a team, invite a second user, and verify role restrictions.
3. Create and rotate an API key; verify expiry and revocation.
4. Connect one cloud provider and confirm ingestion reaches the dashboard.
5. Trigger a forecast, anomaly scan, report, and scheduled job.
6. Complete Stripe checkout and verify the signed webhook updates entitlement.
7. Confirm tenant A cannot read or mutate tenant B data.
8. Stop Redis, PostgreSQL, and a worker in turn; confirm alerts and recovery.
9. Restore a database backup into a fresh environment.

## Handover decision

The repository can be handed to another startup for evaluation and deployment
once the automated release gates pass. It should only be described as
production-live for that startup after its own credentials, infrastructure,
email/billing flows, backup restore, monitoring, security review, privacy
policy, terms, and incident ownership have been completed.
