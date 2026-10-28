# Client identity, rate limiting and SSE through the proxy

How the API decides who a request is from, which headers it trusts, and what
each deployment must configure. Code: `backend/app/core/client_ip.py`,
`backend/app/core/rate_limit.py`, `backend/app/auth/brute_force.py`,
`apps/app/lib/api-proxy.ts`.

## Trust boundary

```
Browser ──> [edge: Vercel / ALB / nginx] ──> Next.js /api/* proxy ──> FastAPI (uvicorn)
```

1. **FastAPI** starts from the TCP peer address. It reads `X-Forwarded-For`
   only when that peer is listed in `TRUSTED_PROXY_IPS` (IPs or CIDRs, empty by
   default). It walks the header right to left, skips trusted hops, and takes
   the first untrusted address. Each entry must be a bare IPv4/IPv6 address,
   otherwise the whole header is ignored. `Forwarded`, `X-Real-IP` and
   similar headers are never trusted.
2. **uvicorn** must run with `--no-proxy-headers` (all launch configs in this
   repo do). Otherwise uvicorn applies its own rule (trust `127.0.0.1`) before
   the app sees the request, and the two rules disagree.
3. **The Next.js proxy** strips every forwarding header the browser sends. It
   sets `X-Forwarded-For` only from `TRUSTED_CLIENT_IP_HEADER`: a header that
   the edge in front of Next.js writes, and overwrites if a client sends it.

If a trusted proxy doesn't forward a usable client address, the API treats it
as a **shared** client: many users may be behind it, so it is never locked out
or put behind a CAPTCHA as a whole.

## What uses the identity

| Control | Keyed by | Limit |
|---|---|---|
| API rate limit, logged-in users | verified session (JWT signature, expiry, not logged out) | `RATE_LIMIT_MAX_REQUESTS` / window |
| API rate limit, API keys | the key, plus a per-client ceiling across all keys | limit, and 5x limit per client |
| API rate limit, anonymous | client address (IPv6 grouped by /64) | `RATE_LIMIT_MAX_REQUESTS` / window |
| Login rate | account+client / account / client | 5 / 10 / 30 per minute (300 for a shared proxy) |
| Login CAPTCHA | account failures / client failures | 3 / 10 |
| Login lockout (15 min) | account failures / client failures | 5 / 20 |

A lockout also refuses the correct password. Unknown and registered emails get
the same responses. If Redis is down, logins and rate-limited requests fail with
503 rather than going unprotected.

## Configuration by deployment

| Deployment | `TRUSTED_PROXY_IPS` (API) | `TRUSTED_CLIENT_IP_HEADER` (Next.js) |
|---|---|---|
| Local dev, Next and API on one machine | `127.0.0.1,::1` | unset |
| Local dev, API in Docker, Next on the host | the Docker gateway address the API sees (e.g. `192.168.65.1`) | unset |
| Next.js on Vercel, API behind an ALB | the ALB subnets (CIDRs) | `x-real-ip` |
| Self-hosted nginx in front of Next.js | the Next.js server addresses | header nginx sets with `proxy_set_header X-Real-IP $remote_addr;` |
| API called directly (no proxy) | empty | n/a |

With `TRUSTED_CLIENT_IP_HEADER` unset, logged-in users and API keys still get
their own buckets. Anonymous traffic and the client-level login limits then
treat the Next.js server as one shared client. Set the header only when an edge
you control is guaranteed to overwrite it. If Next.js is reachable directly, a
client could send that header and choose its own address.

These settings are not verified in any deployed environment yet. Check them per
environment before relying on per-client limits.

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
worker) expires with its lease.
