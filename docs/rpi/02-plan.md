# Heliox — Plan of Action to Market-Ready (RPI · Plan)

Date: 2026-10-27 · Input: [`01-research.md`](01-research.md) · Status: **approved 2026-10-27 · Phase 1 in progress (1.1, 1.2, 1.4 done; branches local, not yet merged)**

## Goal

> A stranger can find Heliox, sign up free, install the agent or connect a
> cloud account, see **correct** per-model and per-team GPU cost within 15
> minutes, and upgrade to Growth with a real card.

Each phase ends with an exit check that must pass before the next phase starts.
Each code task becomes its own branch and PR, with tests, in the **Implement**
step.

Owner key:
- **Eng:** code, which Claude can implement.
- **Founder:** accounts, money, legal or customers. Only you can do these.

Estimates are rough, for one engineer.

---

## Phase 0 · Decisions and accounts (Founder, ~2–3 days, runs in parallel with Phase 1)

| # | Task | Unblocks |
|---|---|---|
| 0.1 | Confirm that `heliox.ai` is owned and who holds DNS (or pick a new domain) | P0-1, P0-3, P1-7 |
| 0.2 | Pick launch hosting. **Recommendation:** use the existing Terraform on AWS, but start with one small environment, not the full HA setup. | P0-1 |
| 0.3 | Create an AWS deploy role and add GitHub OIDC secrets; create a durable `INTEGRATIONS_ENCRYPTION_KEY` in Secrets Manager and back it up | P0-1 |
| 0.4 | Get sandbox accounts with read-only billing access for AWS, GCP and Azure (permissions listed in `DEEP_AUDIT.md` §CLOUD) | P0-7 |
| 0.5 | Get Terms, Privacy, DPA and refund policy drafted (template service + counsel review) | P0-6 |
| 0.6 | Decide on `/proxy`: build it or cut it. **Recommendation:** cut it from v1. | P0-3 |
| 0.7 | Line up 3–5 design partners and note their stack (K8s / Slurm / Ray / cloud) | P1-1 priority |
| 0.8 | Verify the sending domain in Resend; activate Stripe live mode (once 0.5 is done) | P1-7, Phase 3 |

---

## Phase 1 · Make the core path correct (Eng, ~1.5–2 weeks)

**Exit check:** on a local or staging stack, a free team installs the agent on
a GPU node (or the agent's simulated mode in CI). It sees real utilization, and
the per-model costs add up to total spend. No page promises a feature that
doesn't exist.

| # | Task | Fixes | Acceptance criteria |
|---|---|---|---|
| 1.1 ✅ | **Remove the `/proxy` page** (or hide it behind a feature flag) and remove every link to `proxy.heliox.ai` | P0-3 | No route or link to `/proxy` in production builds; the e2e route list is updated. **Done:** `feat/remove-proxy-page` |
| 1.2 ✅ | **Fix the GPU agent** (see the sub-list below) | P0-2 a–h | Unit tests cover the payload math; an image builds in CI; the agent refuses to start without NVML unless `--mock` is passed. **Done:** `feat/gpu-agent-fixes` (23 agent tests, live mock run, migration 034) |
| 1.3 | **Unify cost attribution** in one `services/attribution.py`. Split each day's spend by GPU-seconds, matched on (date, provider, gpu_type). Leftover spend goes to an "unattributed" bucket. The analytics route and the assistant both call it. Fix the README to match. **Also:** base idle waste's expected hours on GPU count, not `cost-days × 24`; normalize the GCP provider to `gcp` (with a data migration). | P0-5 | Property test: per-model costs + unattributed = total spend; the assistant and the dashboard return the same numbers for the same window; an 8-GPU fleet at 50% shows 50% idle |
| 1.4 ✅ | **Free tier gets 1 ingest-only API key** (agent/SDK only, no read API). Keep `api_access=False` for the read API. | P0-4 | A free team can create exactly one ingest key; `/ingest/*` accepts it; read endpoints still reject it. **Done:** `feat/free-tier-ingest-key` (migration 033) |

**Merge note:** migrations 033 (1.4) and 034 (1.2) both follow 032. Whichever
branch merges second must set its `down_revision` to the other's revision.
| 1.5 | **Add legal pages:** `/terms`, `/privacy`, `/dpa`, linked from signup (with a checkbox), the footer and Stripe checkout. The text comes from 0.5; until then, placeholder pages show a draft banner. | P0-6 | Signup records the terms version and acceptance time |
| 1.6 | **Repo hygiene:** remove the committed `backend/.venv311/`; move the root `*_SUMMARY.md`, `*_AUDIT*.md` and similar files into `docs/archive/`; keep README, LICENSE and ARCHITECTURE at the root | P1-9 | Root has under 15 files; no build or test regressions |

**1.2 Agent fixes:**
- Ship `agent/Dockerfile` and publish it in CI to GHCR (`heliox-agent`).
- Fix `pynvml` name decoding.
- Fail loudly instead of falling back to mock data.
- Report *allocated* GPU-seconds and *utilization* as separate fields.
- Make `--send-costs` default to off, and actually toggleable.
- Read the API key from an env var or file, never argv.
- Auto-detect the provider from cloud metadata.
- Read the K8s downward API (node, pod, namespace, labels).
- Delete `agent/k8s-daemonset.yaml` and make the Helm chart the one install path.

**Order:** 1.1 → 1.4 → 1.2 → 1.3 → 1.5 → 1.6. The first two are quick wins;
1.2 and 1.3 are the core of the phase.

---

## Phase 2 · Deploy and verify against real customers (Eng + Founder, ~2 weeks)

**Exit check:** `app.<domain>` is live with TLS. At least one real cloud
account has synced. Two design partners have the agent running and have
confirmed their numbers are plausible.

| # | Task | Fixes | Acceptance criteria |
|---|---|---|---|
| 2.1 | **Get the deploy pipeline green:** OIDC auth, run migrations *before* the new tasks take traffic, deploy staging on merge to `main` and production on tag | P0-1 | One green deploy to staging and one to production; rollback tested |
| 2.2 | **Sync a real sandbox for each cloud** (AWS → GCP → Azure); fix whatever breaks; record evidence | P0-7 | Connect → sync → view → disconnect works on a real account; credentials are revoked on disconnect |
| 2.3 | **Collect jobs automatically from Kubernetes.** The agent and a small controller create and close `jobs` rows from pod lifecycle, using configurable labels (`heliox.ai/model`, `team`, `env`). Then mark the Kubernetes integration as live in the UI. | P1-1, P1-6 | A pod labeled with a model shows up under cost-by-model with no manual API call |
| 2.4 | **Publish the packages:** the `heliox` SDK and CLI on PyPI, the agent image, and a Helm repo (GitHub Pages) | P1-3 | `pip install heliox` and `helm repo add heliox …` work from a clean machine |
| 2.5 | **Customer docs site** (Mintlify/Docusaurus at `docs.<domain>`): quickstart, agent install, cloud connector guides, API reference from OpenAPI, and the cost methodology from 1.3 | P1-2 | Every link in the app resolves; the quickstart is tested by someone outside the team |
| 2.6 | **Onboarding first-value:** use sample data until real data arrives; show an agent and connector install checklist with live "data received" status | — | Median time-to-first-chart under 15 minutes, measured with partners |
| 2.7 | **Frontend error tracking** (Sentry for Next.js), plus uptime checks on the API and app | P1-5 | Errors from the browser show up in Sentry; an uptime alert sends a page |

---

## Phase 3 · Paid launch (Eng + Founder, ~1–2 weeks)

**Exit check:** a real card pays for Growth on production, and every
public-facing surface is in place.

| # | Task | Fixes |
|---|---|---|
| 3.1 | **Landing and pricing pages** (`/` for visitors, the app for signed-in users). Pricing shows Starter / Growth $199 / Enterprise and matches `core/plans.py`. | P1-4 |
| 3.2 | **Stripe live mode:** live keys, a live webhook endpoint, a tax setting, and the customer portal; one real end-to-end purchase and refund | Phase 0.8 |
| 3.3 | **Product analytics** (PostHog): signup → connect → first data → upgrade funnel | P1-8 |
| 3.4 | **Support and trust:** a status page, a support inbox or Intercom, a basic SLA for Growth, and a security page (build on `docs/enterprise/SECURITY_WHITEPAPER.md`) | P1-8 |
| 3.5 | **Ops drills:** restore RDS from backup into staging; run the load test against staging; write and test an on-call runbook | P2 infra |

---

## Phase 4 · After launch: enterprise and scale (backlog, not part of the launch)

| Item | Note |
|---|---|
| GPU inventory via `ec2:Describe*` / GCE / Azure Compute | Prior audit CLOUD-07 |
| Execute SOC 2 Type I (Vanta/Drata) | The checklist exists |
| SCIM, audit-log export, data residency | Enterprise asks |
| Slurm, Ray and SageMaker job collectors | Based on what design partners use (0.7) |
| Datadog integration | Currently "Coming soon" |
| MIG / multi-GPU-per-pod accounting | Agent v2 |
| Inference proxy | Only if 0.6 says to build it; needs its own security review |

---

## Rough timeline

```
Week:     1        2        3        4        5        6        7
Phase 0  ████                                                    (founder, parallel)
Phase 1  █████████████
Phase 2               ██████████████████
Phase 3                                  ██████████████
                                       ▲ design-partner beta  ▲ paid launch
```

That's about **6–7 weeks to a paid launch** if Phase 0 doesn't stall. Phase 1
needs no founder input except 0.6, so it can start now.

## Implement step: how we'll run it
- **One task per branch and PR.** Each PR's description names the finding ID
  it closes.
- **Tests come first** for 1.2, 1.3 and 1.4: a failing test that reproduces
  the finding, then the fix.
- **Updates as we go:** after each phase, this plan and `01-research.md` are
  updated with ✅ and evidence. No new summary docs at the repo root.

## Risks
- **Attribution changes (1.3) shift the numbers customers see.** Version the
  method and show it in the "explain" output.
- **The free ingest key (1.4) widens the abuse surface.** Keep per-key rate
  limits and a cap on ingest volume.
- **Phase 2 depends on design partners.** If none are ready, test on our own
  cloud GPU node to unblock 2.3 and 2.6.
