# Client identity, rate limiting and SSE through the proxy

How the API decides who a request is from, which headers it trusts, and what
each deployment must configure. Code: `backend/app/core/client_ip.py`,
`backend/app/core/rate_limit.py`, `backend/app/auth/brute_force.py`,
`apps/app/lib/api-proxy.ts`.

**Status:** this has been verified locally only (unit tests and an isolated
Docker stack). No staging or production deployment has been checked. Don't rely
on per-client identification in an environment until it has been verified
there.

## Trust boundary

```
Browser ──> [edge: Vercel / ALB / nginx] ──> Next.js /api/* proxy ──> FastAPI (uvicorn)
```

1. **FastAPI** starts from the TCP peer address. It reads `X-Forwarded-For`
   only when that peer is listed in `TRUSTED_PROXY_IPS` (IPs or CIDRs, empty by
   default). It walks the header right to left, skips trusted hops, and takes
   the first untrusted address. Each entry must be a bare IPv4/IPv6 address;
   otherwise the whole header is ignored and the proxy itself is the identity.
   `Forwarded`, `X-Real-IP` and similar headers are never trusted.
2. **uvicorn** must run with `--no-proxy-headers` (every launch config in this
   repo does). Otherwise uvicorn applies its own rule (trust `127.0.0.1`) before
   the app sees the request, and the two rules disagree. If a rewritten peer is
   detected, the API logs a warning.
3. **The Next.js proxy** strips every forwarding header the browser sends
   (`X-Forwarded-*`, `Forwarded`, `X-Real-IP`, `CF-Connecting-IP`, …). It sets
   `X-Forwarded-For` only from `TRUSTED_CLIENT_IP_HEADER`: a header that the
   edge in front of Next.js writes, and overwrites if a client sends it. It
   uses the last entry, which is the one the edge itself wrote, and drops any
   value that isn't a valid IP.

### Shared identities

Some identities stand for many users. They are marked **shared**, and are never
locked out or put behind a CAPTCHA as a whole:

- a trusted proxy that didn't forward a usable client address;
- any internal, non-routable address: loopback, RFC 1918, CGNAT
  (100.64.0.0/10), link-local, IPv6 ULA. Internet clients can't connect from
  these addresses, so such a peer is infrastructure, such as a Next.js server,
  load balancer or Docker gateway. This is the fail-safe when nobody configured
  `TRUSTED_PROXY_IPS`.

Per-account protections always apply, whatever the client identity.

## What uses the identity

| Control | Keyed by | Limit |
|---|---|---|
| API rate limit, logged-in users | verified session (JWT signature, expiry, not logged out) | `RATE_LIMIT_MAX_REQUESTS` / window |
| API rate limit, API keys | the key, plus a per-client ceiling across all keys | limit, and 5x limit per client |
| API rate limit, anonymous | client address (IPv6 grouped by /64) | `RATE_LIMIT_MAX_REQUESTS` / window |
| Login rate | account+client / account / client | 5 / 10 / 30 per minute (300 for a shared client) |
| Login CAPTCHA | account failures / individual-client failures | 3 / 10 |
| Login lockout (15 min) | account failures / individual-client failures | 5 / 20 |

If Redis is down, logins and rate-limited requests fail with 503 rather than
going unprotected.

## Lockout tradeoffs

- **Account lockout is a denial-of-service lever.** Anyone who knows an email
  address can lock that account for 15 minutes by failing 5 logins, and can
  keep it locked by repeating. A lockout also refuses the correct password.
  This is the price of stopping distributed password guessing against one
  account. If it becomes a problem, the usual mitigations are a CAPTCHA
  instead of a hard lock, or step-up verification.
- **No account enumeration through lockouts.** Counters, CAPTCHA and lockout
  apply to any submitted email, registered or not, with the same responses.
  One existing gap is unrelated to this change: login is measurably faster for
  unknown emails, because no password hash is checked.
- **CAPTCHA needs hCaptcha.** If `HCAPTCHA_SECRET_KEY` isn't set, a required
  CAPTCHA can't be solved, so it behaves like a lockout until the counters
  expire (15 minutes).
- **Behind a shared NAT**, users share a client identity: 10 failures across
  accounts from one public address require CAPTCHA from that address, and 20
  lock it for 15 minutes.

## Required ingress and network restrictions

- **List only proxy hosts in `TRUSTED_PROXY_IPS`.** Anything in those ranges
  can claim any client address. Never list ranges shared with untrusted
  workloads (a whole multi-tenant VPC, `0.0.0.0/0`, or a Docker gateway on a
  host where untrusted processes run).
- **Restrict who can reach the API** (security group, ingress or network
  policy) to the trusted proxies, plus any intended direct API clients. Direct
  clients are fine: they're identified by their own address. They just must not
  originate from a trusted range.
- **Set `TRUSTED_CLIENT_IP_HEADER` only if** the edge overwrites that header on
  every request and Next.js can't be reached except through that edge. If
  clients can reach Next.js directly, they can pick their own address.
- **Edges that append** (`X-Forwarded-For` on an ALB or nginx with
  `$proxy_add_x_forwarded_for`) are handled: the last entry is the address the
  edge saw.

## Configuration by deployment

| Deployment | `TRUSTED_PROXY_IPS` (API) | `TRUSTED_CLIENT_IP_HEADER` (Next.js) | Per-client identity |
|---|---|---|---|
| Local dev, Next and API on one machine | `127.0.0.1,::1` | unset | no (shared) |
| Local dev, API in Docker, Next on the host | the Docker gateway the API sees (e.g. `172.24.0.1`) | unset | no (shared) |
| Self-hosted nginx in front of Next.js, Next → API on a private network | the Next.js server addresses | `x-real-ip`, with nginx `proxy_set_header X-Real-IP $remote_addr;` | yes |
| Next.js on Vercel, API on a public endpoint | the API's load balancer, plus Vercel dedicated egress IPs if you have them | `x-real-ip` | only with dedicated egress IPs (see below) |
| API called directly (no proxy) | empty | n/a | yes |

**Vercel → public API:** the request reaches the API from a Vercel egress
address on the internet. Without dedicated egress IPs listed in
`TRUSTED_PROXY_IPS`, the API sees that public address as one individual client.
All app users would then share its login CAPTCHA and lockout thresholds, which
lets an attacker lock everyone out. Don't use this topology without dedicated
egress IPs; route Next.js → API over a private network instead. This topology
is unverified.

With no edge header, logged-in users and API keys still get their own
buckets, and logins are protected per account. Only anonymous traffic and the
client-level login limits are pooled for the shared identity.

## Redis keys

- Login: `heliox:login:v2:*`. The old `heliox:login_*` keys are no longer read
  and expire within 15 minutes.
- API rate limit: `rl:<bucket>:<window>` with a 2-window TTL. Buckets in the old
  format age out within 2 minutes.
- SSE slots: `heliox:events:conn_leases:<team>`, a sorted set of connection
  leases (75 s, renewed by every 30 s ping). The old `heliox:events:conns:*`
  counters expire within 60 seconds.

## SSE through the proxy

The proxy streams response bodies as they arrive and adds `no-transform` to
`text/event-stream` responses, so compression doesn't buffer them. Closing the
browser's EventSource cancels the upstream request, so the API releases the
team's connection slot. A slot that is never released (for example, a crashed
worker) expires with its lease. Five concurrent streams are allowed per team.
