# Heliox — Market-Readiness Audit (RPI · Research)

Date: 2026-10-27 · Base: `main` @ `98e5b7c` · Method: Research → Plan → Implement

This is the **Research** phase: what exists, what was verified, and what stands
between Heliox and a stranger signing up, connecting their GPUs, and paying.
The **Plan** is in [`02-plan.md`](02-plan.md). Nothing is implemented until the
plan is approved.

Earlier audits (`docs/DEEP_AUDIT.md`, `AUDIT.md`,
`docs/PRODUCTION_MARKET_READINESS_AUDIT.md`) covered security, auth, Stripe and
route coverage in depth. This audit does not repeat them. It asks a different
question: **can a real customer get value end to end?**

Every finding is labelled:

- **Verified here:** reproduced in this audit, with file and line.
- **From prior audit:** taken from the existing audit docs, not re-run.

---

## 1. Verdict

**Not market-ready. The engineering base is strong, but the customer path is broken.**

The backend, auth, billing and dashboard are well built and well tested.
The parts a customer touches *first* are the weakest:

1. There is no live deployment.
2. The GPU agent can't run as shipped.
3. Free users can't send data.
4. One page asks customers to route their OpenAI keys through a server that
   doesn't exist.

None of these is a hard engineering problem. They are mostly "last mile" gaps.

| Area | State |
|---|---|
| Backend API, data model, migrations | ✅ Solid |
| Auth, RBAC, SSO, tenant isolation | ✅ Solid (prior audit, 8/8) |
| Stripe test-mode billing | ✅ Solid (prior audit, 7/7) |
| Dashboard UI (25 routes) | ✅ Solid |
| Tests / CI | ✅ Good |
| **Live deployment / domain** | ❌ None |
| **GPU agent (core data source)** | ❌ Can't run as shipped, and its data is wrong |
| **Free → paid funnel** | ❌ Free tier can't ingest |
| **Cost attribution correctness** | ⚠️ Two code paths disagree |
| **Real cloud verification** | ⚠️ Never run against a real account |
| **Legal / marketing / docs** | ❌ Missing |

---

## 2. What has been built (and works)

### Verified here
- **The full stack runs locally.** Postgres 15, Redis 7, FastAPI, Celery
  worker and beat all come up. All 32 Alembic migrations apply. The API serves
  `/health` and `/docs`. The Next.js app serves on :3000.
  - Two compose bugs (beat crash loop, false-unhealthy worker) were fixed in
    PR #5.
- **The backend tests pass: 303 / 303.**
  - One test failed whenever a local `.env` existed; that is fixed in PR #5.
- **CI is broad.** It runs lint, type check, unit tests, dependency scan,
  security scan, frontend build and a Docker build with a Trivy scan.
  - PR #5 makes the Docker build tolerate a failed GitHub Actions cache upload.
- **Breadth of the backend:**
  - 38 route modules (~10k LOC) and 25 SQLAlchemy models.
  - 25 services: forecasting, anomaly detection, budget guardrails,
    recommendations, reports, Slack and email notifications, inference cost
    attribution, experiments, an ROI dashboard and an AI assistant.
- **Cloud billing connectors are real code, not stubs:**
  - AWS Cost Explorer (442 LOC).
  - GCP BigQuery billing export (492 LOC).
  - Azure Cost Management (530 LOC).
- **Frontend:** 25 routes covering dashboard, analytics, forecast, budgets,
  alerts, recommendations, reports, ROI, billing, onboarding, settings, SSO and
  shared reports. There are Playwright e2e specs.
- **Infrastructure as code:**
  - Terraform for ECS Fargate, RDS, ElastiCache, ALB and Route53.
  - A Helm chart with api, worker, beat, migrations, redis and agent templates.
- **Developer tooling:** a CLI with commands for agent, anomalies, auth,
  budgets, config, costs, inference and jobs.

### From prior audit (`docs/DEEP_AUDIT.md`, 2026-07-30)
- Auth hardening passed 8/8: session revocation, IDOR, RBAC, brute-force
  limits, CORS.
- The Stripe test-mode lifecycle passed 7/7: checkout, decline, webhook,
  entitlement change, cancel.
- Integration credentials are encrypted at rest (Fernet), and production
  refuses to start without a key.
- The browser route-coverage suite passed 46/46, and `pip-audit` was clean.

---

## 3. Findings: what blocks real customers

Severity scale:
- **P0:** blocks launch.
- **P1:** blocks paid launch / scale.
- **P2:** later.

### P0-1 · Nothing is deployed and the domains don't resolve. *(Verified here)*
- **Deploy workflow:** `Deploy to AWS` has failed on every run on `main`. The
  error is `Credentials could not be loaded` at "Build & Push to ECR"; there
  are no AWS secrets in the repo.
- **Domains:** `heliox.ai`, `app.heliox.ai` and `api.heliox.ai` don't resolve.
- **Dead links in the app:** it points to `docs.heliox.ai`, `proxy.heliox.ai`
  and `support@`/`sales@heliox.ai`. All are dead or unverified.
- **Why it matters:** nobody can sign up.
- **Open question:** whether the `heliox.ai` domain is actually owned.

### P0-2 · The GPU agent (the core data source) can't run, and its data would be wrong. *(Verified here)*

The README promises a "one-line agent deploy via Kubernetes DaemonSet".

**It can't run as shipped:**

| # | Problem | Where |
|---|---|---|
| a | The DaemonSet uses a bare `python:3.11-slim` image and never installs `requests`/`pynvml`. It crashes on import. The ConfigMap it mounts isn't shipped. It has no GPU runtime, tolerations or node selector. | `agent/k8s-daemonset.yaml` |
| b | The Helm agent template points at `ghcr.io/heliox-ai/heliox-agent`. **No Dockerfile or workflow builds that image.** | `charts/heliox/values.yaml:123` |
| c | If `pynvml` is missing or NVML fails, the agent **silently sends mock data** (`mock-gpu`, 50% utilization) to production. | `agent/heliox_agent.py:20-24` |
| d | `nvmlDeviceGetName(...).decode()` crashes on current `pynvml`, which returns `str`. | `heliox_agent.py:32` |
| e | The API key is passed as a CLI argument, so it is visible in `ps` and pod specs. | `heliox_agent.py`, DaemonSet |

**Its data would be wrong even if it ran:**

| # | Problem | Where |
|---|---|---|
| f | ~~Mixes up allocated and utilized hours.~~ **Corrected during 1.2:** idle waste treats `gpu_hours` as *busy* hours against 24 paid hours/day (`analytics.py:486-502`), so `utilization × interval` is the right quantity. The real problem was accuracy: one reading per interval, multiplied by the nominal interval instead of the measured one. | `heliox_agent.py:69` |
| g | `--send-costs` is `store_true` with `default=True`, so it **can't be turned off**. The agent posts cost *estimates* from a hard-coded price table, which double-counts against real billing data from the cloud connectors. | `heliox_agent.py:112` |
| h | The provider is hard-coded to `"local"`, and no pod, namespace or node labels are sent. **Per-job, per-team and per-model attribution from the agent is impossible.** | `heliox_agent.py` |

### P0-3 · The `/proxy` page advertises a service that doesn't exist and asks for customers' OpenAI keys. *(Verified here)*
- **What the page says:** `apps/app/app/proxy/page.tsx` tells users to set
  `base_url="https://proxy.heliox.ai/v1"` and send their OpenAI API key through
  it.
- **What actually exists:** no proxy server is in the repo, and the domain
  doesn't resolve.
- **Why it's urgent:** this is a broken promise. If anyone else controls that
  domain, it is also a credential-harvesting risk.
- **Remove or gate it before any public traffic.** (The prior audit's
  HXA-008 already flagged unsubstantiated claims on this page.)

### P0-4 · The free tier can't send any data. *(Verified here)*
- **The limit:** `core/plans.py` gives Starter (free) `max_api_keys=0` and
  `api_access=False`, enforced at `api/routes/teams.py:315`.
- **The conflict:** the agent, the SDK, the CLI and `/ingest/*` all need a
  team API key.
- **What a free user is left with:** one cloud *billing* connector (no per-job
  attribution) or CSV import.
- **Why it matters:** the free tier can't show the product's core value, which
  kills a product-led trial.

### P0-5 · "Cost per model" gives different answers in different places. *(Verified here)*

| Where | Method | Problem |
|---|---|---|
| Dashboard `GET /analytics/cost/by-model` (`analytics.py:181-205`) | Splits **all** daily spend by job runtime share | Ignores GPU type and provider, so a T4 job gets a share of H100 spend |
| AI assistant (`services/assistant.py:330-378`) | Gives each model the **full** window spend of every (provider, GPU) pair it ran on | **Double-counts.** Models sharing a GPU type each get 100% of it, so the per-model sum can exceed total spend |
| README "How Heliox Calculates Cost" | "join jobs → cost_snapshots on (provider, gpu_type, date)" | Matches neither implementation |

For a cost product, numbers that disagree are a trust-killer. We need one
attribution service, used by every caller, with a test that per-model costs
add up to total spend.

**Found while doing 1.2 (all verified):**

| Finding | Where | Status |
|---|---|---|
| `usage_snapshots.gpu_hours` was `NUMERIC(12,2)`, so each 60-second agent report was rounded before summing. A 25%-busy GPU stored 0.00 every minute; a 50% one was overstated by 20%. | `models/cost.py:110` | **Fixed in 1.2** (migration 034, `NUMERIC(14,6)`) |
| Idle waste's "expected hours" is `cost-days × 24` per GPU type, whatever the fleet size. An 8-GPU fleet reports up to 192 busy hours against 24 expected, so it never shows waste. | `analytics.py:486`, `:687` | Open, moved into 1.3 |
| The GCP connector stores `provider="gcp_billing_bigquery"` while AWS and Azure store `aws`/`azure`, so GCP agent usage (`gcp`) never joins to GCP billing. Fixing it needs a data migration of existing rows. | `gcp_billing_bigquery.py:470,482` | Open, moved into 1.3 |

### P0-6 · There are no legal pages. *(Verified here)*
- **What's missing:** no Terms of Service, Privacy Policy, DPA or refund policy
  anywhere in `apps/app`.
- **Why it's required:**
  - Heliox stores customers' **cloud credentials and billing data**.
  - Stripe live mode needs published terms and a refund policy.
  - Enterprise buyers will ask for a DPA.
- **This is required before taking signups or payments.**

### P0-7 · No cloud connector has ever synced a real account. *(From prior audit, CLOUD-01–04)*
- AWS, GCP and Azure connect/sync/disconnect have only been tested against
  mocks.
- "Multi-cloud" can't be marketed until each connector has synced at least one
  sandbox account.
- The prior audit lists the exact read-only permissions needed.

### P1 findings: needed for a paid launch

| ID | Finding | Evidence |
|---|---|---|
| P1-1 | **Job attribution has no automatic source.** Per-job, per-model and per-team cost needs `jobs` rows, but only `POST /jobs` creates them, by hand. The SDK only sends usage (`sdk/heliox_sdk.py`, 31 lines). There's no Kubernetes label collection and no MLflow, W&B or Ray integration. | `sdk/`, `agent/` |
| P1-2 | **No customer docs.** `docs.heliox.ai` is linked but doesn't exist. Agent install, SDK and API guides aren't published. | `proxy/page.tsx:148` |
| P1-3 | **Nothing is published as a package or image.** There's no `pip install heliox`, no agent image and no Helm repo. | repo, workflows |
| P1-4 | **No landing or pricing page.** `/` is the authenticated app. Pricing is defined in code (Starter free, Growth $199/mo, Enterprise custom) but never shown to a visitor. | `apps/app/app/page.tsx`, `core/plans.py` |
| P1-5 | **No frontend error tracking.** The backend uses Sentry; the Next.js app has none. | `grep sentry apps/app` |
| P1-6 | **Kubernetes and Datadog are shown as "Coming soon"** in the integrations page, even though Kubernetes is the agent's whole story. | `settings/integrations/page.tsx:185-205` |
| P1-7 | **Email deliverability isn't proven.** Verification and password-reset emails go through Resend from `alerts@heliox.ai`, a domain that isn't verified (see P0-1). | `.env.example` |
| P1-8 | **No status page, support channel, SLA or product analytics** (funnel, activation, retention). | — |
| P1-9 | **Repo hygiene:** a virtualenv is committed (`backend/.venv311/`), and there are ~70 overlapping summary/audit docs at the repo root, several with conflicting "production-ready" claims. This confuses contributors and diligence reviewers. | repo root |

### P2 findings: enterprise and scale (after launch)
- **No GPU inventory.** The cloud connectors read billing data only; none lists
  live instances or GPUs. *(From prior audit, CLOUD-07.)*
- **Enterprise:** a SOC 2 checklist exists but nothing has been executed; there
  are no audit-log export, data-residency or SCIM features.
- **Multi-cluster agent:** the agent needs provider and cloud auto-detection,
  plus MIG and multi-GPU-per-pod accounting.
- **Infra validation:** the restore drill, a load test on production-like
  infrastructure, and multi-AZ failover have not been run.

---

## 4. What a customer experiences today

| Step | Today |
|---|---|
| Find Heliox | ❌ No site, the domain doesn't resolve |
| Sign up | ❌ No deployment (✅ works locally) |
| Agree to terms | ❌ No terms |
| Onboard (Welcome → Create team → Connect data → Alerts) | ✅ UI exists |
| Connect a cloud billing account | ⚠️ Code exists, never run against a real account |
| Install the GPU agent | ❌ Crashes, no image, sends wrong or mock data |
| Send usage data on the free plan | ❌ Free plan can't create API keys |
| See cost per model or team | ⚠️ Needs jobs entered by hand, and the two calculations disagree |
| Get alerts (Slack, email) | ✅ Built (email domain unverified) |
| Upgrade to Growth | ✅ Stripe test mode works; ❌ live mode needs legal pages |

---

## 5. Remaining unknowns (founder input needed)
1. Is `heliox.ai` registered and controlled by us? Who holds the DNS?
2. Hosting: AWS (as in Terraform) or something simpler (Fly, Render, Vercel +
   Railway) for launch?
3. Which design partners are lined up, and which cloud and orchestrator do they
   use (Kubernetes, Slurm, Ray, SageMaker)? This decides what P1-1 integrates
   with first.
4. Is the inference proxy (`/proxy`) a real roadmap item or a mock-up?
5. Who signs off on Terms, Privacy and DPA (a template service or counsel)?
