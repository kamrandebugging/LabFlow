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

- `trusted_proxies static private_ranges` so `X-Forwarded-For` handling uses the
  trusted peer and the app reads the **last** hop.
- `request_body { max_size 5MB }` on `/api/*` (second 413 layer).
- `/internal/*` blocked publicly.
- `/admin/*` should carry an `ADMIN_ALLOWED_IPS` allowlist; see the Caddyfile
  comment. Do not expose the admin without it in production.

There is no `rate_limit` directive in the stock `caddy:2.8.4` image (it needs
the `caddy-ratelimit` plugin). Application throttling is the enforced layer;
add the plugin only if you also rebuild the Caddy image.

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

## 4. Acceptance test (the "one laptop" test)

Run a single-IP k6 burst against staging's login endpoint:

```
k6 run --vus 50 --duration 60s scripts/k6-login-burst.js
```

Expected: HTTP 429 with `Retry-After` after the budget, **zero 5xx**, the worker
stays up, and a fake leftmost `X-Forwarded-For` does not reset the bucket
(the app reads the last hop). Record the result in the LAB-49 evidence folder.
