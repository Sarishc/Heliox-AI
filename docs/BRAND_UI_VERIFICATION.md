# Heliox Brand and UI Verification

Verified on July 29, 2026 against the native local stack (PostgreSQL, Redis,
FastAPI, and Next.js; Docker was not required).

## Release gate

| Gate | Result |
| --- | --- |
| Backend test suite | 298 passed |
| Frontend production build | 25 routes compiled and generated |
| Browser end-to-end suite | 9 passed |
| Production dependency audit | No known pnpm vulnerabilities |
| Python production dependency audit | No known vulnerabilities |
| Production route smoke test | 21 of 21 routes returned HTTP 200 |
| Git whitespace validation | Passed |

The browser suite covers registration, login, logout, protected-route access,
malformed/expired sessions, wrong-password feedback, responsive auth layouts,
long input, and mobile form validation.

## Lighthouse

Lighthouse 12.8.2 was run against the production Next.js server.

| Surface | Performance | Accessibility | Best practices | SEO |
| --- | ---: | ---: | ---: | ---: |
| Login | 81 | 95 | 100 | 100 |
| Protected-entry redirect | 79 | 95 | 96 | 100 |

The protected-entry measurement starts at `/` without a session and ends at the
login/onboarding redirect by design. Authenticated dashboard behavior is covered
by the Playwright end-to-end suite rather than being represented as an
authenticated Lighthouse score.

## Responsive evidence

- `docs/screenshots/brand-ui/login-375.png`
- `docs/screenshots/brand-ui/login-768.png`
- `docs/screenshots/brand-ui/login-1440.png`
- `docs/screenshots/brand-ui/wrong-password.png`
- `docs/screenshots/brand-ui/signup-validation-mobile.png`

## Notes

- Authentication errors remain inline and use an accessible alert region.
- Reduced-motion preferences disable non-essential page, chart, KPI, and toast
  animation.
- The billing current-month test now uses the same UTC calendar contract as the
  API, preventing false failures around the UTC day boundary.
