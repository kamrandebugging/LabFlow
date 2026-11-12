# Edge / DDoS hardening (LAB-49 Phase 2.7 and 2.7b)

The "one kid with a laptop" scenario is OWASP API4: no rate limit + no firewall
means a trivial request flood takes the lab down. Controls are layered:

## 1. Application layer (implemented)

- `DEFAULT_THROTTLE_CLASSES` in `backend/config/settings/base.py`:
  reads 600/min/user, writes 300/min/user, 3,000/min/tenant.
  Every 429 carries `Retry-After` (`apps/core/exceptions.py`).
- Login 5/15 min per (tenant, email), 20/15 min per (tenant, IP), progressive
  1-hour lock after three throttled windows.
- TOTP verify 10/15 min per account, independent of challenge freshness.
- Refresh 30/min/IP; public demo requests 5/hour/IP; callbacks 120/min/IP;
  report portal 60/min/IP plus 60/10 min per token and 20 invalid tokens/hour.
- Body cap 5 MB (`PayloadLimitMiddleware` → 413) and invoice `items` max 200.
- Container limits: backend 1 GB/2 CPU, worker 1.5 GB/2 CPU, postgres 1 GB/2 CPU,
  redis 256 MB/1 CPU, minio 512 MB/1 CPU (`docker-compose.yml`).

## 2. Caddy (implemented)

- `trusted_proxies static private_ranges` trusts the Docker/RFC1918 peer; the
  app reads the **last** trusted hop and honours `CF-Connecting-IP` only when
  the immediate peer is in `TRUSTED_PROXY_CIDRS`. A Cloudflare-proxied
  deployment **must** add Cloudflare's published ranges to both Caddy's
  `trusted_proxies` and `TRUSTED_PROXY_CIDRS`; with only `private_ranges`, all
  clients appear as one edge IP and per-IP limits/audit IPs are wrong.
- `request_body { max_size 5MB }` on `/api/*` (second 413 layer).
- `/internal/*` blocked publicly.
- `/admin/*` is **not** IP-gated by default. Before production, add a Caddy
  `remote_ip` matcher using `ADMIN_ALLOWED_IPS` (the env var is documented in
  `.env.example`); until then Django's own auth is the only gate. The checked-in
  inventory records this as an operator step, not an implemented control.

There is no `rate_limit` directive in the stock `caddy:2.8.4` image (it needs
the `caddy-ratelimit` plugin). Application throttling is the enforced layer;
add the plugin only if you also rebuild the Caddy image.

## 2b. Client-facing 429 contract (implemented)

Every throttled response is `429` with `Retry-After` (seconds) and a stable
`rate_limited` error code. Defaults:

| Scope | Budget |
|---|---|
| Authenticated reads | 600/min/user |
| Authenticated writes | 300/min/user, 3,000/min/tenant |
| Login | 5/15 min per tenant+email, 20/15 min per tenant+IP |
| TOTP verify | 10/15 min per account (bound to the server challenge user) |
| Refresh | 30/min/IP |
| Report access | 60/min/IP, 120/10 min/IP, 60/10 min/token, 20 invalid/hour/IP |
| Demo requests | 5/hour/IP |
| n8n callbacks | 120/min/IP |
| Exports | 1/hour/tenant; downloads 60/min/IP |

A Redis outage makes the public report-portal and core throttles fail **closed**
(429), not open. Clients should honour `Retry-After` and back off.

## 3. Cloudflare WAF + CDN (deployment checklist, 2.7b)

Cloudflare is already the DNS provider (Doc 10). In the dashboard:

1. Proxy the apex and `*.<base-domain>` records (orange cloud).
2. SSL/TLS mode: Full (strict); enable Always Use HTTPS and HSTS (6 months+).
3. WAF managed rules: enable the Cloudflare Managed Ruleset + OWASP Core Ruleset
   in block mode.
4. Rate-limiting rule: `/api/v1/auth/login`, `/api/v1/auth/totp/verify`,
   `/api/v1/auth/password-reset/*` — 20 requests / minute / IP, action block
   with a 60-second timeout. Second rule for `/api/v1/*`: 600/minute/IP.
5. Bot Fight Mode: on for the apex marketing site; exclude `/api/*` if it breaks
   legitimate SPA traffic — the app-level limits still apply.
6. Under Attack Mode is the manual break-glass switch.
7. Keep the origin IP out of DNS history (proxied records only); firewall the
   VPS so only Cloudflare IP ranges reach ports 80/443.
8. Set `TRUSTED_PROXY_CIDRS` (and Caddy `trusted_proxies`) to the Cloudflare
   ranges from <https://www.cloudflare.com/ips/> so the app sees the real client
   IP instead of the edge IP.

## 4. Acceptance test (the "one laptop" test)

Run a single-IP k6 burst against staging's login endpoint:

```
k6 run --vus 50 --duration 60s scripts/k6-login-burst.js
```

Expected: HTTP 429 with `Retry-After` after the budget, **zero 5xx**, the worker
stays up, and a fake leftmost `X-Forwarded-For` does not reset the bucket
(the app reads the last hop). Record the result in the LAB-49 evidence folder.
