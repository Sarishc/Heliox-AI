# Heliox-AI Production Readiness Audit

Audit date: 2026-07-29  
Audited commit: `d4d71c65fc7f09e566aa37909859e0f8ef4d5e1a`  
Audit branch: `hardening/audit-fixes`

## 1. Executive summary

**Handover-ready for customer-specific deployment: Yes, with launch gates.**

The original audit blockers have been remediated locally. The native
PostgreSQL/Redis stack starts without Docker, the schema migrates through
Alembic `032`, all 298 backend tests pass, the Next.js production build
generates all 25 routes, and all three browser journeys pass. Both production
dependency audits report no known vulnerabilities.

This does not make an adopter production-live automatically. Each startup still
needs its own production credentials, managed infrastructure, domain/TLS,
email and billing verification, monitoring, backup restore exercise, legal
documents, security review, and incident ownership. See
`docs/STARTUP_HANDOVER.md`.

Current verified gates:

- Native PostgreSQL and Redis connectivity: **PASS**
- Migration through Alembic `032 (head)`: **PASS**
- FastAPI startup and health endpoint: **PASS**
- Backend suite: **298 passed**
- Frontend locked install and 25-route production build: **PASS**
- Playwright signup/onboarding/dashboard/logout and auth guards: **3 passed**
- `pnpm audit --prod`: **no known vulnerabilities**
- `pip-audit -r backend/requirements-prod.txt`: **no known vulnerabilities**
- Docker/Compose image execution: **UNVERIFIED**; native operation is the
  supported verified path for this handover

The hosted environment is also unverified. `.github/workflows/deploy.yml`
targets an AWS App Runner production environment on every push to `main`, so
`main` must be treated as potentially serving real traffic.

## 2. Blockers

### HXA-001 — Critical — Backend cannot start with documented local Redis URL

- Location: `backend/app/core/cache.py:32-40`
- Reproduction:
  1. Start a reachable Redis server.
  2. Set `REDIS_URL=redis://localhost:56379/0`.
  3. Start `uvicorn app.main:app`.
  4. Startup aborts with `Redis client could not be created`.
  5. Calling `redis.from_url(..., ssl_cert_reqs=None).ping()` exposes
     `TypeError: AbstractConnection.__init__() got an unexpected keyword
     argument 'ssl_cert_reqs'`.
- Impact: Local development, CI's plain Redis service, and any non-TLS Redis
  deployment cannot boot. Security middleware then returns 503 throughout the
  test suite.
- Fix: Pass `ssl_cert_reqs` only for `rediss://` URLs and add regression tests
  for both `redis://` and `rediss://` client construction.

### HXA-002 — Critical — Frontend production build imports a missing module

- Location: `apps/app/components/BetaAccessGate.tsx:5`
- Reproduction:
  1. Run `pnpm install --frozen-lockfile`.
  2. Run `pnpm --filter app build`.
  3. Turbopack exits with `Module not found: Can't resolve
     '@/lib/beta-access'`.
- Impact: No production frontend artifact can be built or deployed. Visiting
  `/recommendations` in development returns HTTP 500 and triggers the build
  error overlay.
- Fix: Restore a tested beta-access implementation or remove the obsolete
  client-only beta gate in favor of real server-side authorization. Treat the
  latter as an auth architecture change requiring product approval.

### HXA-003 — High — Main branch can deploy despite missing frontend verification

- Location: `.github/workflows/ci.yml:63-127`,
  `.github/workflows/deploy.yml:3-8`
- Reproduction:
  1. Inspect CI jobs: only backend lint/tests and backend Docker build run.
  2. Observe no pnpm install, frontend lint, frontend test, or frontend build.
  3. Observe production deploy runs directly on pushes to `main`.
- Impact: The exact missing-module failure in HXA-002 is invisible to required
  CI and can coexist with a production deployment.
- Fix: Add locked frontend install, ESLint, typecheck, tests, and production
  build as required jobs. Make deployment depend on the complete CI workflow.

## 3. Security

### HXA-004 — High — Runtime dependency set contains known high-severity CVEs

- Location: `apps/app/package.json:11-30`,
  `backend/requirements.txt:1-73`
- Reproduction:
  1. Run `pnpm audit --audit-level=low`.
  2. Observe 67 advisories, including runtime Next.js advisories affecting
     `next@16.1.1`.
  3. Run `pip-audit -r backend/requirements.txt --desc`.
  4. Observe 16 advisories in five packages, including FastAPI/Starlette request
     parsing and denial-of-service issues.
- Impact: Public request parsing and React Server Component surfaces include
  known denial-of-service and request-handling weaknesses.
- Fix: Upgrade in reviewed, bounded groups with changelog review and regression
  tests. At minimum, move Next.js to a release that fixes all listed advisories
  and move FastAPI/Starlette to a compatible patched pair. Do not apply a blind
  bulk upgrade.

### HXA-005 — High — Security scans and type checking are explicitly non-blocking

- Location: `.github/workflows/ci.yml:57-61`,
  `.github/workflows/ci.yml:129-146`, and the Trivy steps later in the file
- Reproduction: Inspect `continue-on-error: true` on mypy, `pip-audit`, Trivy
  filesystem scan, Trivy image scan, and SARIF upload.
- Impact: Known critical/high findings and type errors do not prevent merge or
  deployment.
- Fix: Establish a reviewed baseline, fail on newly introduced high/critical
  runtime findings, and make type checking blocking after resolving the current
  backlog.

### HXA-006 — High — CI skips security-sensitive and tenant-isolation tests

- Location: `.github/workflows/ci.yml:107-120`
- Reproduction: Observe explicit ignores for reports, tenant isolation security,
  Stripe metering, OAuth session, and OAuth token encryption suites.
- Impact: Regressions in tenant isolation, session handling, token encryption,
  billing, and report sharing can merge undetected. The full local suite shows
  failures in all of these areas.
- Fix: Repair and re-enable every skipped suite. Do not reduce coverage by
  deleting or further skipping tests.

### HXA-007 — Medium — CSRF protection is disabled by default

- Location: `backend/app/core/config.py` (`CSRF_PROTECTION_ENABLED` default),
  `backend/app/middleware/csrf.py:57-60`
- Reproduction: Start with production settings without explicitly setting
  `CSRF_PROTECTION_ENABLED`; the middleware immediately delegates without
  validation.
- Impact: Cookie-authenticated state-changing requests lack the intended
  double-submit protection if deployment configuration omits this flag.
- Fix: Enable CSRF by default for staging and production in configuration
  validation, then verify login, logout, OAuth callback, and all mutation flows.
  This changes authentication behavior and requires an approved rollout plan.

### HXA-008 — Medium — Public product claims are hard-coded and unsubstantiated

- Location: `apps/app/app/proxy/page.tsx:21-22,107-112`
- Reproduction: Visit `/proxy` after resolving the compile blocker and inspect
  the hard-coded `2.4B+` requests, `<2ms` p99, `99.99%` SLA, 12 providers, and
  `https://proxy.heliox.ai/v1`.
- Impact: Customers may be shown fabricated operational metrics and an endpoint
  that was not verified in this audit, creating legal and trust risk.
- Fix: Source claims from measured production telemetry or clearly mark the
  screen as a mock/demo and remove public SLA/usage assertions.

Secrets in current tracked files were not observed during targeted inspection.
Git-history secret scanning remains unverified until a dedicated history scanner
is available; cloud credentials and GitHub Actions secrets are inaccessible.

## 4. Correctness

### HXA-009 — High — Full backend suite has 45 failures

- Location: multiple; primary independent failures include
  `backend/app/api/routes/budgets.py`,
  `backend/app/services/cost_ingestion.py`,
  `backend/app/models/team_member.py`,
  `backend/app/auth/oauth_google.py`, and report services.
- Reproduction: Run `PYTHONPATH=. pytest tests/ --cov=app -q` from `backend`
  with required local environment values.
- Impact: Billing usage, invitations, onboarding, OAuth sessions, report
  generation, cost attribution, tenant isolation, SAML, and metering are not
  supported by a passing regression suite.
- Evidence: `248 passed, 45 failed`; failures include unexpected 503 responses,
  stale function signatures, missing `TeamRole.MEMBER`, UUID strings passed to
  UUID columns, tuple/schema mismatches, and stale mock call counts.
- Fix: First remove the Redis cascade (HXA-001), rerun, then triage only the
  residual failures. Each product bug requires a regression test; stale tests
  require confirmation against intended business behavior.

### HXA-010 — Medium — Frontend and backend local port defaults conflict

- Location: `apps/app/app/api/[...path]/route.ts:7`,
  `apps/app/next.config.ts:3-6`, `README.md` local run instructions
- Reproduction: Start the backend using the documented port `8000` and start the
  frontend without `API_PROXY_TARGET`; server-side API traffic targets `8001`.
- Impact: A nominally successful local frontend start cannot reach the backend,
  producing misleading offline/loading behavior.
- Fix: Standardize the default on port 8000 and document `API_PROXY_TARGET` in
  `.env.local.example`.

## 5. Reliability

### HXA-011 — High — Production deploy publishes before migration execution

- Location: `.github/workflows/deploy.yml`; migration execution exists only in
  separate provisioning scripts under `aws/setup/05_run_migrations.sh`
- Reproduction: Follow the deploy workflow: it builds, updates App Runner, and
  health-checks the new image without running or gating on Alembic migrations.
- Impact: A code release requiring a new schema can receive production traffic
  before the schema exists, causing startup or request failures.
- Fix: Add a pre-traffic, idempotent migration job with backup/rollback
  safeguards and deployment gating. This changes the migration architecture and
  requires approval before implementation.

### HXA-012 — Medium — Redis diagnostics discard the actionable exception

- Location: `backend/app/core/cache.py:42-47`
- Reproduction: Cause any Redis client construction error and inspect logs;
  only the exception type is recorded, not its message.
- Impact: Operators see `TypeError` without the invalid argument or root cause,
  extending outages and obscuring configuration defects.
- Fix: Log a sanitized exception message without credentials or full Redis URL.

External API retries, timeout behavior, Celery worker/beat execution, and
provider failure modes are not runtime-verified because the API cannot start and
provider credentials were not supplied.

## 6. Performance

- No trustworthy endpoint latency benchmark can be produced until the stack
  boots.
- The repository contains indexes through migration `031`, rollup models,
  caching, and Prometheus instrumentation, but this audit did not validate query
  plans or p95/p99 behavior.
- The production frontend bundle size is unavailable because the build fails.
- Existing performance reports in the repository are historical claims, not
  evidence for the audited commit.

## 7. Enterprise readiness gaps

Present in code but not end-to-end verified: team RBAC, audit log model, SAML
configuration, integration credential encryption, report sharing, billing
entitlements, and tenant-scoped models.

Material gaps or unverified controls:

- Tenant-isolation security tests are excluded from CI and currently fail.
- OAuth session and token-encryption tests are excluded and currently fail.
- No verified backup/restore or disaster recovery exercise.
- No verified data export/deletion workflow for GDPR requests.
- No verified audit-log immutability, retention, or customer export.
- No verified SSO certificate rotation or break-glass process.
- No verified production key rotation for JWT, OAuth, Slack, or integration
  encryption keys.
- No evidence of SOC 2 control operation was supplied.

## 8. Developer experience

A new engineer cannot currently clone and run the product in 15 minutes:

- Docker is assumed by primary instructions but the frontend is absent from
  Compose.
- Native startup is blocked by HXA-001.
- Production frontend build is blocked by HXA-002.
- Frontend/backend port defaults conflict.
- Redis is described as optional in some documentation but is a hard startup
  dependency.
- Deployment documentation alternates between Railway, ECS/Terraform, Vercel,
  Helm, and App Runner without a single authoritative path.
- A partial virtual environment is tracked under `backend/.venv311`.

## 9. Test coverage

Observed total backend line coverage: **57%**.

Highest-risk low-coverage areas include authentication routes, SAML, integration
routes, report generation, email delivery, cloud/task workers, and tenant
resolution. The frontend has one Playwright specification, but CI neither runs
it nor builds the frontend. No meaningful frontend coverage figure is produced.

The most important missing passing gates are:

1. Full tenant-isolation suite against PostgreSQL.
2. Cookie session + CSRF + logout/blacklist lifecycle.
3. Signup, verification, password reset, and invitation journeys.
4. Migration-plus-startup smoke test using the supported Redis schemes.
5. Frontend build and authenticated dashboard smoke test.
6. Provider timeout/retry/idempotency tests.
7. Billing webhook replay and concurrency tests.

## 10. Prioritized fix plan

### P0

| Finding | Work | Estimate |
|---|---|---:|
| HXA-001 | Correct Redis client construction and add scheme tests | 0.5 day |
| HXA-002 | Restore/remove missing beta-access module with tests | 0.5–1 day |
| HXA-003 | Add required frontend CI build/test gate | 0.5 day |
| HXA-009 | Rerun suite after Redis fix and repair true critical-flow failures | 2–5 days |

### P1

| Finding | Work | Estimate |
|---|---|---:|
| HXA-004 | Reviewed runtime dependency upgrades | 1–3 days |
| HXA-005 | Make type/security gates enforceable | 1 day |
| HXA-006 | Re-enable skipped sensitive suites | 2–4 days |
| HXA-007 | CSRF production-default proposal and rollout | 1–2 days |
| HXA-010 | Align proxy defaults and environment documentation | 0.25 day |
| HXA-011 | Migration-before-traffic deployment proposal | 1–2 days |
| HXA-012 | Improve sanitized Redis diagnostics | 0.25 day |

### P2

| Finding | Work | Estimate |
|---|---|---:|
| HXA-008 | Replace unverified marketing/operational claims | 0.5 day |
| DX gaps | Consolidate deployment and setup documentation | 1–2 days |
| Coverage | Expand frontend, task-worker, and external failure testing | 3–5 days |
| Enterprise | Backup/restore, retention, export/deletion, key rotation exercises | 1–2 weeks |

## Fix disposition

| Finding | Status | Notes |
|---|---|---|
| HXA-001 | Fixed locally | P0; plain/TLS Redis scheme regression tests pass |
| HXA-002 | Fixed locally | P0; module restored and production build passes |
| HXA-003 | Fixed locally | P0; frontend locked install and production build are now required in CI |
| HXA-004 | Fixed locally | FastAPI/Next and transitive packages upgraded; PyJWT replaced the unpatched python-jose/ecdsa chain; both production audits are clean |
| HXA-005 | Open | P1 |
| HXA-006 | Fixed locally | P1; previously skipped auth, report, billing and tenant suites are enabled |
| HXA-007 | Deferred | Auth behavior change; proposal/approval required |
| HXA-008 | Open | P2 |
| HXA-009 | Fixed locally | P0; full backend suite passes: 298 passed |
| HXA-010 | Fixed locally | Frontend proxy default and example environment now use backend port 8000 |
| HXA-011 | Deferred | Migration architecture change; proposal/approval required |
| HXA-012 | Open | P1 |

## Hardening progress

Safe P0 work completed locally:

- HXA-001: Redis construction now passes TLS-only options only for `rediss://`.
  `backend/tests/test_redis_required.py`: 16 passed.
- HXA-002: restored the beta-access helper, fixed the email-verification API
  import, and wrapped the login search-parameter consumer in Suspense.
  `pnpm --filter app build`: passed, all 25 pages generated.
- Corrected the `UsageEvent.event_metadata` ORM attribute to map to the existing
  `metadata` column created by migration 018. This avoids a migration and has a
  schema-contract regression test.
- Corrected the demo seed's nonexistent password-hashing function import.

The approved API-key expiry design is implemented in migration 032 and enforced
by the authentication model. The migration is at head, demo seeding completes,
the production frontend generates all 25 routes, and the complete backend suite
passes (298 tests). Browser verification covers signup, login, onboarding,
dashboard loading, logout, Analytics, and Opportunities.

Dependency hardening upgraded FastAPI to 0.141.1, Pydantic to 2.13.4,
pydantic-settings to 2.14.2, SQLAlchemy to 2.0.43, Alembic to 1.16.5, Redis to
6.4.0, HTTPX to 0.28.1, and Next.js to 16.2.11. The health route remains an
exact `/api/v1/health` endpoint for load balancers, and the test suite now
validates exposed paths through the OpenAPI contract.
