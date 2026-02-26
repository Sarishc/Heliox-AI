# Heliox CI/CD Pipeline

Phase 6 — Production-grade CI/CD with code quality gates.

## Pipeline Overview

| Job | Description |
|-----|-------------|
| **Lint** | Black + Ruff |
| **Type Check** | mypy |
| **Unit Tests** | pytest with 80% coverage |
| **Dependency Scan** | pip-audit |
| **Security Scan** | Trivy filesystem |
| **Build** | Docker image + Trivy image scan |
| **Integration Tests** | Docker Compose + smoke + load test |

## Quality Gates

- **80% minimum test coverage** — enforced via `--cov-fail-under=80`
- **No merge if tests fail** — all jobs must pass
- **Dependency vulnerabilities** — pip-audit (continue-on-error for now)
- **Docker image vulnerabilities** — Trivy (results in Security tab)

## Running Locally

```bash
# Lint
cd backend && black --check app tests && ruff check app tests

# Type check
cd backend && mypy app --ignore-missing-imports

# Unit tests with coverage
cd backend && pip install -r requirements.txt
SECRET_KEY=dev pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80

# Dependency scan
pip install pip-audit && pip-audit -r backend/requirements.txt

# Docker build + Trivy
docker build -t heliox-api ./backend
trivy image heliox-api
```

## Branch Protection

To enforce CI before merge, configure in GitHub:

1. Settings → Branches → Add rule
2. Branch name: `main` (and `develop`)
3. Require status checks: `lint`, `unit-tests`, `build`, `integration-tests`
4. Require branches to be up to date

## Coverage

Coverage report is uploaded to Codecov (if configured). Excluded:
- `tests/`
- `alembic/`
- `__init__.py`
