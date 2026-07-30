# Heliox Deep Audit

Date: 2026-07-30  
Branch: `verification/deep-audit` from `hardening/audit-fixes` at `8a228ea`  
Environment: native PostgreSQL `55432`, Redis `56379`, FastAPI `8000`,
Next.js `3000`; Stripe CLI test mode only.

## 1. Executive summary

**Phase 1 — Authentication: 8 PASS, 0 FAIL, 0 UNTESTABLE.** Live adversarial
requests confirmed session revocation, tenant isolation, RBAC enforcement,
throttling, malformed/expired-token rejection, and CORS denial. Password and
reset-token storage were also exercised. Bandit reported no medium/high auth
findings. The application uses a 30-minute HS256 session whose secret is
required from the environment; it does not issue application refresh tokens.

**Phase 2 — Stripe: 7 PASS, 0 FAIL, 0 UNTESTABLE.** A real Stripe test-mode
account, product, recurring price, two frontend signups, hosted Checkout, a
successful `4242` subscription, a `4000…0002` decline, signed webhook delivery,
database entitlement transition, and customer-portal cancellation were
executed. Three payment defects found during the run were fixed and covered:
string-backed enum serialization, missing subscription metadata/webhook retry
behavior, and current Stripe API cancellation-period compatibility.

**Phase 3 — Cloud integrations: 1 PASS, 2 FAIL, 4 UNTESTABLE.** No AWS, GCP, or
Azure connector/sandbox credentials are available, so no real connect/sync/
disconnect claim is made. Encryption-at-rest code and 36 focused tests pass,
but this environment has no persistent `INTEGRATIONS_ENCRYPTION_KEY`, and the
implemented providers ingest billing/cost data rather than independent compute
inventory. Real-provider acceptance remains customer-credential dependent.

**Phase 4 — Feature coverage: 42/46 scenarios PASS and 4/46 FAIL once
asynchronous errors are observed.** The new suite exercises all 25 public,
protected, dynamic, and API-proxy surfaces plus empty, populated/demo, and
representative write paths. Three failures expose calls made by `/` and
`/settings/authentication`; one more is the expected 404 from a deliberately
invalid invite link that the strict console-error assertion records. The honest
route-level result is **23/25 clean**. Billing and forecast now pass both state
variants.

**Market-readiness decision:** the payment flow is now suitable for test-mode
acceptance, but the overall product remains **NO-GO for unrestricted production
handoff** until the two noisy route surfaces, Python tool advisories, persistent
integration encryption key, and at least one real cloud sandbox connection are
resolved. Paid onboarding is no longer blocked by the audited Stripe path.

## 2. Phase 1 — Authentication hardening

### AUTH-01 — Token configuration and expiry

- Outcome: **PASS**
- Severity: High if absent
- Fix status: Verified
- Evidence:
  - `backend/app/auth/security.py` pins `ALGORITHM = "HS256"` and a 30-minute
    access-token expiry.
  - `SECRET_KEY` is required through settings; no fallback secret is present in
    the authentication module.
  - Decode calls pin `algorithms=[ALGORITHM]`; `none` is not accepted.
  - Application refresh tokens are not issued, so there is no refresh bearer
    token to rotate or replay. Expiry requires a new login.
  - Targeted test output:

```text
tests/test_auth_deep_audit.py ..   [100%]
2 passed
```

  - `test_expired_session_token_is_rejected` signs an otherwise valid expired
    token and receives HTTP 401 from `/api/v1/teams/`.

### AUTH-02 — Password and reset-token storage

- Outcome: **PASS**
- Severity: Critical if weak/plaintext
- Fix status: Verified
- Evidence:

```text
{'scheme': '2b', 'cost_factor': 12, 'hash_prefix_only': '$2b$12'}
```

  - Passwords use bcrypt with cost 12.
  - Reset tokens are generated from 48 random URL-safe bytes, stored only as a
    SHA-256 digest, expire after 60 minutes, and are cleared after use.
  - The new regression test proves the raw token differs from storage, has a
    future expiry, works once, and cannot be looked up after reset.

### AUTH-03 — Logout and captured-token replay

- Outcome: **PASS**
- Severity: Critical
- Fix status: Verified
- Evidence from `node work/deep-audit/auth_attack.mjs`:

```json
{
  "own_protected_read": 200,
  "logout": 200,
  "captured_token_replay": 401,
  "malformed_token": 401
}
```

The raw session was never printed; evidence records only SHA-256 prefix
`8937b6b4aa675e62`.

### AUTH-04 — Cross-tenant IDOR

- Outcome: **PASS**
- Severity: Critical
- Fix status: Verified
- Evidence:

```json
{
  "user_b_reads_user_a_team": 403,
  "user_b_updates_user_a_team": 403
}
```

User A's tested team was `028d062c-9b86-48e0-8131-8b4e40f6c61e`.

### AUTH-05 — Brute-force throttling

- Outcome: **PASS**
- Severity: Critical
- Fix status: Verified
- Evidence: 20 rapid invalid logins against one account returned:

```text
401, 401, 401, 400, 400,
429, 429, 429, 429, 429, 429, 429, 429, 429, 429,
429, 429, 429, 429, 429
```

The CAPTCHA gate starts after three failures; rate limiting throttled 15 of 20
requests. Redis is fail-closed for this control.

### AUTH-06 — RBAC

- Outcome: **PASS**
- Severity: Critical
- Fix status: Verified
- Evidence:

```json
{"ordinary_user_calls_admin_teams": 403}
```

This was a direct API request, not a hidden-UI assertion.

### AUTH-07 — CORS

- Outcome: **PASS**
- Severity: High
- Fix status: Verified
- Evidence:

```json
{
  "preflight_status": 400,
  "allow_origin": null
}
```

Origin `https://attacker.invalid` was not reflected and received no
`Access-Control-Allow-Origin`.

### AUTH-08 — Auth-focused SAST

- Outcome: **PASS**
- Severity: Informational
- Fix status: Reviewed
- Tool: Bandit 1.8.6 against `backend/app/auth`, `auth.py`, and
  `auth_oauth.py`.
- Evidence:

```text
1,883 lines scanned
HIGH: 0
MEDIUM: 0
LOW: 6
```

The six low findings are one OAuth token-endpoint URL incorrectly recognized as
a hardcoded password and five deliberate `try/except/pass` compatibility paths.
No secret, unsafe JWT algorithm, shell injection, or weak hash was reported.

## 3. Phase 2 — Stripe test-mode payment flow

No live key or live charge was used.

### PAY-01 — Test account and tooling

- Outcome: **PASS**
- Severity: Required evidence
- Fix status: Verified
- Evidence:

```text
Stripe CLI 1.40.9
account: acct_1TUYLsQ6lgK40Qro
country: US
charges_enabled: false
payouts_enabled: false
```

The CLI default is test mode. An isolated test product and price were created:

```json
{
  "product_id": "prod_Uyw69o4Tpx0p1W",
  "price_id": "price_1TyyE3Q6lgK40QroSEe6LVkQ",
  "currency": "usd",
  "unit_amount": 4900,
  "interval": "month",
  "livemode": false
}
```

### PAY-02 — Signup and Stripe customer creation

- Outcome: **PASS**
- Severity: Required evidence
- Fix status: Verified
- Evidence:
  - The real `/signup` UI created isolated success and decline tenants.
  - The authenticated user opened the real `/billing` UI.
  - Backend/Stripe logs:

```text
POST https://api.stripe.com/v1/customers -> 200
Created Stripe customer cus_UywkemX4bDjz6J
```

### PAY-03 — Hosted Checkout and successful test card

- Outcome: **PASS**
- Severity: Critical
- Fix status: Fixed after explicit owner approval
- Evidence:

```text
Hosted Checkout: Sandbox
Card: Visa ending 4242
Redirect: http://localhost:3000/billing?success=true
Stripe invoice: in_1TyysfQ6lgK40QrokL64Qc8e
Stripe subscription: sub_1TyyshQ6lgK40QrozhO7YAt9
```

The initial string-backed enum serialization 500 was fixed by normalizing the
stored plan/status at the response boundary. The HTTP regression test proves a
persisted subscription returns 200 with `free`/`active`.

### PAY-04 — `invoice.paid` webhook and database transition

- Outcome: **PASS**
- Severity: Critical
- Fix status: Fixed and verified
- Evidence:

```text
invoice.paid: evt_1TyysiQ6lgK40Qro8DYE3KC9 -> HTTP 200
checkout.session.completed: evt_1TyysjQ6lgK40QroVo3YW4zh -> HTTP 200
team_subscriptions: growth | active | subscription_id present
team_entitlements: growth
fresh browser: paid_ui_growth=visible manage_button=true
```

Checkout metadata is now also sent through `subscription_data.metadata`.
The completed-Checkout handler repairs older metadata-less subscriptions and
syncs them. Unexpected processing failures now return 500 so Stripe retries
instead of silently losing the state transition.

### PAY-05 — Declined card

- Outcome: **PASS**
- Severity: High
- Fix status: Verified
- Evidence: hosted Checkout with `4000 0000 0000 0002` displayed
  `Your credit card was declined. Try paying with a debit card instead.`
  The browser remained usable, and the isolated tenant stayed `free` with no
  Stripe subscription ID.

### PAY-06 — Cancellation/refund

- Outcome: **PASS**
- Severity: High
- Fix status: Fixed and verified
- Evidence: the app-created Stripe Customer Portal showed the paid invoice and
  Visa ending 4242. Cancellation was confirmed in the portal, which displayed
  `Cancels Aug 30` and retained service through the paid period.

```text
customer.subscription.updated: evt_1Tyz7vQ6lgK40QrohPObACxf -> HTTP 200
database: growth | active | cancel_at_period_end=true
```

Current Stripe API versions use an explicit `cancel_at` timestamp for this
portal flow even when `cancel_at_period_end` is false. Sync now maps either
representation to the local scheduled-cancellation flag. Immediate downgrade
would be incorrect while the paid period remains active.

### PAY-07 — Secret exposure

- Outcome: **PASS**
- Severity: Critical
- Fix status: Verified
- Evidence: the compiled static bundle contains zero `sk_live_`/`sk_test_`
  matches. Four source files match `sk_test_`, all under `backend/tests/` and
  all synthetic fixture values. No application source or browser bundle
  contains a Stripe secret; checkout returns a hosted URL.

## 4. Phase 3 — AWS/GCP/Azure integrations

### CLOUD-01 — Connector and sandbox availability

- Outcome: **UNTESTABLE**
- Severity: Required evidence
- Fix status: Needs customer's own credentials
- Evidence: plugin discovery returned no callable AWS, GCP, Azure, or cloud
  security connector. Environment presence checks were false for
  `AWS_ACCESS_KEY_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, and `AZURE_CLIENT_ID`.

Minimum read-only alternatives:

- AWS: access key/secret for a sandbox principal with
  `sts:GetCallerIdentity` and `ce:GetCostAndUsage`; Cost Explorer must be
  enabled. A read-only compute-inventory implementation would additionally
  need `ec2:DescribeInstances` and related `Describe*` permissions, which the
  current provider does not call.
- GCP: a sandbox project with BigQuery billing export enabled and a service
  account granted BigQuery Data Viewer on the billing dataset.
- Azure: tenant ID, client ID, client secret, subscription IDs, and Cost
  Management Reader on those sandbox subscriptions.

No admin/write cloud scope is requested.

### CLOUD-02 — Real connect and saved “Connected” state

- Outcome: **UNTESTABLE**
- Severity: High
- Fix status: Needs customer's own credentials
- Reason: no provider sandbox credential or connector is available. No fake
  connection was submitted.

### CLOUD-03 — Real cost sync and expected interval

- Outcome: **UNTESTABLE**
- Severity: High
- Fix status: Needs customer's own credentials
- Reason: no real connection. The stored default sync interval is 60 minutes;
  manual sync is also exposed.

### CLOUD-04 — Real disconnect/revocation

- Outcome: **UNTESTABLE**
- Severity: High
- Fix status: Needs customer's own credentials
- Reason: no real provider connection exists to revoke.

### CLOUD-05 — Encryption at rest

- Outcome: **PASS**
- Severity: Critical
- Fix status: Verified in code/tests
- Evidence:
  - Database column: `integration_connections.config_encrypted TEXT NOT NULL`.
  - Connect routes call `Fernet.encrypt_config` before persistence and decrypt
    only at use time.
  - Focused output:

```text
tests/test_auth_deep_audit.py .......... 2 passed
tests/test_oauth_token_encryption.py ... 9 passed
tests/test_cloud_integrations_e2e.py ... 25 passed
36 passed in 4.30s
```

These provider tests use sandboxed/mocked SDK boundaries and prove application
logic, not a real provider connection.

### CLOUD-06 — Persistent encryption-key configuration

- Outcome: **FAIL**
- Severity: Critical for any saved integration
- Fix status: Needs deployment configuration
- Evidence emitted by the running backend:

```text
INTEGRATIONS_ENCRYPTION_KEY is not set.
A temporary key will be generated for this process —
encrypted tokens will be unreadable after restart.
```

A production secret manager must supply one stable Fernet key before accepting
any customer credential.

### CLOUD-07 — Independent compute/GPU inventory

- Outcome: **FAIL**
- Severity: Medium / capability gap
- Fix status: Needs implementation
- Evidence: AWS uses Cost Explorer, GCP queries BigQuery billing export, and
  Azure uses Cost Management. None enumerates live compute inventory. GPU
  attribution inferred from cost records must not be marketed as verified
  inventory.

## 5. Phase 4 — Full feature coverage

### Route manifest and result

The audit maps the 25 application surfaces below. Every protected page is
loaded once without local demo data and once with populated/demo state; tests
also reject browser runtime errors after asynchronous data loading.

| # | Route/surface | Result | State/write evidence |
|---:|---|---|---|
| 1 | `/` | **FAIL** | Empty state makes two 400 requests; populated state passes |
| 2 | `/alerts` | PASS | Empty/populated; email-alert save 201 |
| 3 | `/analytics` | PASS | Empty and populated |
| 4 | `/billing` | PASS | Empty/populated; real Checkout, decline, webhook, portal cancellation |
| 5 | `/billing/usage` | PASS | Empty and populated |
| 6 | `/budgets` | PASS | Empty/populated; create policy 201 |
| 7 | `/forecast` | PASS | Empty and populated |
| 8 | `/onboarding` | PASS | Authenticated continuation; signup covered |
| 9 | `/optimization` | PASS | Empty and populated |
| 10 | `/proxy` | PASS | Empty and populated |
| 11 | `/recommendations` | PASS load / UNTESTABLE write | Stable empty state; no actionable real record |
| 12 | `/reports` | PASS | Empty/populated; saved-report create 201 |
| 13 | `/roi` | PASS | Empty and populated |
| 14 | `/settings` | PASS | Empty/populated; plan-gated API-key write now shows a visible error |
| 15 | `/settings/authentication` | **FAIL** load / UNTESTABLE SSO write | Both states make a 404 request; no IdP sandbox |
| 16 | `/settings/integrations` | PASS load / UNTESTABLE connect | No cloud sandbox |
| 17 | `/login` | PASS | Public, clean hydration |
| 18 | `/signup` | PASS | Public; real workspace creation used for Stripe |
| 19 | `/forgot-password` | PASS | Public empty state |
| 20 | `/reset-password?token=invalid…` | PASS | Invalid-token state |
| 21 | `/verify-email?token=invalid…` | PASS | Invalid-token state |
| 22 | `/auth/callback?error=access_denied` | PASS | Graceful OAuth denial |
| 23 | `/invite/[token]` | PASS render / strict test FAIL | Expected invalid-token API response is 404 |
| 24 | `/share/[token]` | PASS | Invalid/expired-token state |
| 25 | `/api/[...path]` | PASS | Proxied health response, DB/Redis OK |

Final strict Playwright output:

```text
46 tests
42 passed
4 failed
```

At route level, **23/25 surfaces are clean**. `/` and
`/settings/authentication` emit unexpected failed requests. The invalid invite
route renders its intended error state but also produces an expected 404
console entry, which the deliberately strict test records as a failure rather
than suppressing.

### Previously omitted four routes

The previous 21-route smoke check excluded these dynamic/non-page surfaces:

1. `/api/[...path]` — now verifies the frontend proxy reaches backend health.
2. `/auth/callback` — now verifies an access-denied callback is graceful.
3. `/invite/[token]` — now verifies an invalid token without a 500.
4. `/share/[token]` — now verifies an invalid token without a 500.

### Defects fixed during this phase

1. **Report response contract (High): Fixed.** FastAPI emitted `config_json`
   while the frontend consumed `config`, crashing after a successful report
   create. Report create/list/read/update now serialize the public field name
   through `response_model_by_alias=False`; the real UI create test passes.
2. **SSE Redis connection (Medium): Fixed.** `ssl_cert_reqs` was passed to
   ordinary `redis://`, causing every notification subscriber to fail.
   TLS-only options are now restricted to `rediss://`.
3. **Plan-gated API-key feedback (Medium): Fixed.** A 403 from the Growth plan
   gate produced an unhandled promise and no user feedback. Create/rotate now
   surface the API error; the UI test verifies the visible plan message.
4. **Hydration overlay (Development blocker): Fixed operationally.** The
   screenshot was reproduced as a new-server/old-client class mismatch from
   stale Turbopack chunks. The frontend process had run since before the brand
   commit. After a clean restart, a fresh browser tab showed no overlay and
   zero console warnings/errors. No nondeterministic render code was found.
5. **Stripe state transition (Critical): Fixed.** The subscription response
   now normalizes string-backed enums; Checkout propagates tenant/plan metadata
   to the subscription; completed Checkout repairs legacy metadata; failed
   webhook processing returns non-2xx for retries; and StripeObject/current-API
   period/cancellation representations are normalized.
6. **Billing cache safety (High): Fixed.** Subscription reads use
   `cache: "no-store"` so a post-Checkout browser cannot retain a stale Free
   response.

### Build, regression, and dependency evidence

```text
Backend: 303 passed in 40.32s
Next.js production build: compiled successfully; 25/25 routes generated
pnpm audit --prod: No known vulnerabilities found
pip-audit: 5 advisories in 2 packages
  pytest 7.4.4 -> fix 9.0.3
  black 24.1.1 -> fixes range from 24.3.0 through 26.3.1
```

The Python findings are development/test tooling rather than runtime request
handlers, but pinned vulnerable tooling is still a release-engineering finding
and should be upgraded with the suite rerun before production handoff.

## 6. Still cannot claim

- Any real AWS, GCP, or Azure connection, sync, disconnect, or credential
  revocation. No sandbox credential/connector was available.
- Persistent cloud credential readability across restarts until
  `INTEGRATIONS_ENCRYPTION_KEY` is configured.
- Live GPU/compute inventory from the current cost-only cloud providers.
- Recommendation apply/dismiss behavior against a real actionable record in
  this empty tenant.
- SSO configuration writes against a real Google/SAML/Okta identity provider.
- A fully clean 25-route asynchronous browser run: two surfaces currently emit
  unexpected failed API requests.
- A vulnerability-free pinned Python toolchain until `pytest` and `black` are
  upgraded and the audit is rerun.

## 7. Evidence commands

```bash
node work/deep-audit/auth_attack.mjs
work/audit-venv/bin/bandit -q -r backend/app/auth \
  backend/app/api/routes/auth.py backend/app/api/routes/auth_oauth.py
pnpm exec playwright test e2e/route-coverage.spec.ts --reporter=line
pytest -q tests/test_auth_deep_audit.py \
  tests/test_oauth_token_encryption.py tests/test_cloud_integrations_e2e.py
pnpm --filter app build
pytest -q
```

Sensitive Stripe/API/session values are intentionally absent from this report.
Only test-mode object IDs and a session hash prefix are retained as evidence.

## Follow-up: no-go closure

Date: 2026-07-30

### Closure matrix

| Item | Status | Evidence |
|---|---|---|
| Overview browser noise | **PASS** | The forecast card now requests a typed empty response when a tenant has insufficient history. The normal API contract still returns 400 unless `allow_empty=true`. Isolated browser diagnostics returned document 200 with no console errors, page errors, failed responses, or request failures. |
| Authentication Settings browser noise | **PASS** | The page now fetches the SAML record only when `/teams/sso/settings` reports `saml_configured=true`. This removes the expected-but-noisy 404 for unconfigured teams. No authentication enforcement or authorization logic changed. Isolated browser diagnostics were fully clean. |
| Full route/browser regression | **PASS** | Focused Overview and Authentication Settings run: 3/3 passed. Required route-coverage suite: 46/46 passed. Invalid-token 400/404 responses are explicitly classified as expected negative-path responses rather than ignored globally. |
| Real cloud sandbox | **UNTESTABLE** | No AWS, GCP, or Azure connector or sandbox credentials were available. No demo response is represented as real provider evidence. |
| Persistent credential encryption | **PASS** | Production/staging already refuse startup without a valid `INTEGRATIONS_ENCRYPTION_KEY`. A stable audit key was injected through the environment, a non-live integration fixture was encrypted, PostgreSQL showed only Fernet ciphertext, the backend was restarted, correct-key decryption succeeded, and a different key was rejected. |
| PostgreSQL integration insert | **PASS** | The persistence check exposed and fixed an enum contract defect: SQLAlchemy emitted enum names such as `AWS` while PostgreSQL stores values such as `aws`. Provider, connection status, and sync status now serialize enum values. |
| Python security tooling | **PASS** | `pytest` upgraded 7.4.4 → 9.0.3 and the full backend suite passed 303/303. `black` then upgraded 24.1.1 → 26.3.1 and the full backend suite again passed 303/303. `pip-audit -r requirements.txt` reports no known vulnerabilities. |
| Production frontend build | **PASS** | Next.js compiled and type-checked successfully; 25/25 routes were generated. |

### Browser evidence

- Before: `docs/evidence/overview-failing.png`
- After: `docs/evidence/overview-fixed.png`
- Before: `docs/evidence/authentication-settings-failing.png`
- After: `docs/evidence/authentication-settings-fixed.png`

Both post-fix diagnostics reported:

```text
documentStatus: 200
console: []
pageErrors: []
failedResponses: []
requestFailures: []
```

### Encryption-at-rest evidence

The fixture contains deliberately non-live marker values and cannot access a
cloud account. Raw PostgreSQL evidence:

```text
provider | status   | ciphertext_prefix                                  | length | fernet_shape | plaintext_absent
aws      | disabled | gAAAAABqa6ZIAIb1C1FZiSaOLDVgNLxDwA3VvdiJYgXnce3s… | 204    | true         | true

post_restart_decrypt=PASS
expected_fields_present=True
wrong_key_decrypt=REJECTED
oauth_plaintext_candidates=0
integration_plaintext_candidates=0
```

No earlier plaintext rows were found, so no retroactive credential
re-encryption or rotation was required. The audit key itself is not stored in
the repository or this report. Production deployments must inject a durable
Fernet key from their secret manager and back it up before storing credentials.

### Exact access needed to close the remaining cloud item

Provide one AWS sandbox through an approved connector or short-lived
credentials/role session with only:

```text
sts:GetCallerIdentity
ce:GetCostAndUsage
ec2:DescribeInstances
ec2:DescribeInstanceTypes
ec2:DescribeTags
```

AWS Cost Explorer must be enabled. No write or administrator permission is
needed. Until that access is provided, real connection, sync, GPU inventory,
disconnect, and credential-revocation behavior remain unverified.

### Final verification commands

```bash
pnpm exec playwright test e2e/route-coverage.spec.ts --reporter=line
# 46 passed

pnpm build
# Compiled successfully; TypeScript passed; 25/25 pages generated

REDIS_URL=redis://127.0.0.1:56379/15 PYTHONPATH=. pytest -q
# 303 passed (after pytest upgrade, then again after black upgrade)

pip-audit -r requirements.txt
# No known vulnerabilities found
```

No payment implementation was changed in this follow-up.
