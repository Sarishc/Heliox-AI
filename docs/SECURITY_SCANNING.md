# Security scanning in CI

What the CI security jobs enforce, which findings are knowingly accepted, and
how to add an exception. Workflow: `.github/workflows/ci.yml`. Reviewed
exceptions: `.trivyignore.yaml`.

## Gates

| Job | Step | Blocks the PR when |
|---|---|---|
| Security Scan | Trivy repository scan (blocking) | a CRITICAL/HIGH vulnerability **with a fix available** is in a lockfile or requirements file, or a secret is detected |
| Build Docker Image | Trivy image scan (blocking) | the same, in the built backend image (OS packages and Python packages) |

Both use `aquasecurity/trivy-action` pinned to a verified release commit and
Trivy `v0.76.1`. `ignore-unfixed` keeps advisories that have no fixed version
out of the gate. They're not hidden: each job has a "report (incl. unfixed)"
step that lists every CRITICAL/HIGH finding, and the SARIF upload keeps sending
results to the Security tab. The report and SARIF steps never fail the build,
so reporting problems can't mask or fake a gate result.

Not gated yet:

- **`pip-audit`** (Dependency Scan) runs with `continue-on-error`. It has no
  severity filter, so making it blocking would also fail on medium and low
  advisories. Python CRITICAL/HIGH findings are already gated by Trivy. To
  enforce it later, run it with a reviewed list of `--ignore-vuln` IDs, each
  with an owner and an expiry date.
- **mypy** (Type Check) is still advisory.

## Accepted risks

Reviewed 2026-10-28. Re-check whenever the base image changes, and at least
monthly.

**Debian 13 base image (`python:3.11-slim`): HIGH, no fixed version published.**
Debian lists these as affected or deferred, so no newer package exists. None of
these programs is run by the API or the workers. The image is rebuilt on every
CI run, so fixes are picked up as soon as Debian ships them.

| Advisory | Packages | Debian status |
|---|---|---|
| CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | util-linux family (bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux) | affected |
| CVE-2026-16742 | libsystemd0, libudev1 | affected |
| CVE-2026-54369 | libacl1 | affected |
| CVE-2025-69720 | ncurses (libncursesw6, libtinfo6, ncurses-base, ncurses-bin) | affected |
| CVE-2026-9538 | perl-base | fix deferred |

**setuptools 81.0.0 in the image: one MEDIUM, one LOW advisory (below the
gate).** setuptools 82 and later remove `pkg_resources`, which runtime
dependencies still import (`click_plugins`, `passlib`, `pytz`, `sentry_sdk`).
Upgrading needs those imports gone first.

## Exceptions (false positives)

| Finding | Where | Why it's not a secret |
|---|---|---|
| `gcp-service-account` | `apps/app/components/GCPIntegrationForm.tsx` | Placeholder text showing the shape of a key file; every value is a literal `...` and there's no key material |

To add an exception, prove that no real credential is involved, then add one
entry to `.trivyignore.yaml` with the rule ID, explicit paths and a dated
statement. Never ignore a vulnerability ID there; accepted vulnerabilities go
in the table above.

## Known follow-up (outside CI)

`aws/setup/05_run_migrations.sh` registers the ECS migration task with real
secrets (database URL, `SECRET_KEY`, admin and encryption keys) expanded into
the task definition's plaintext `environment`. Anyone who can read task
definitions can see them. They should become `secrets` entries that reference
the SSM parameters (`valueFrom`), with the task execution role allowed to read
them. That change involves IAM and live secret configuration, so it needs its
own reviewed change.
