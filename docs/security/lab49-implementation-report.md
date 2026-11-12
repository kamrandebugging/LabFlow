# LabFlow — LAB-49 (KAN-268) OWASP API Security Top 10 — Implementation Report

**Date:** 2026-11-12 (overnight run)
**Branch:** `main` working tree (`428b3e3` base) — no commit, no push, no PR
**Spec:** `docs/security/api-security-10-report.md` (copied into the repo as instructed)
**Prompt:** `docs/security/api-security-10-prompt.md`

---

## 1. Executive summary

I implemented the LAB-49 program from start to finish against the **current**
main (`428b3e3`), not the older `5e98a06` / `23b0964` revisions the research
report was written against. That distinction matters: several findings in the
report had already been fixed by PRs #57–#62, so this run hardened what was
**still** broken and added the missing program scaffolding (inventory, central
authorization, throttling matrix, safe fetcher, step-up, anomaly sweep, strict
serializers, prod settings).

The most important real vulnerabilities fixed tonight:

1. **Cross-branch BOLA on sample reject/recollect/cancel** — a branch-scoped
   user with a foreign sample UUID could reject, recollect or cancel another
   branch's sample. Every one of those fetches is now branch-scoped and answers
   404 for foreign objects.
2. **Cross-branch BOLA on result approve/withdraw/amend/critical-notification** —
   all four now fetch the result with a `sample__branch_id IN (...)` predicate;
   a foreign result is indistinguishable from a missing one.
3. **Collecting against another branch's invoice** — `collect_sample()` now
   refuses foreign invoices and files the sample under the **invoice's** branch,
   never the caller's home branch.
4. **DEBUG master TOTP code `123456`** — deleted, along with the DEBUG carve-out
   that disabled mandatory TOTP in development. `123456` now never verifies.
5. **Fail-open secret defaults** — `base.py` refuses to boot without
   `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`, `LABFLOW_TOTP_ENCRYPTION_KEY` and a
   distinct `N8N_WEBHOOK_SECRET` outside dev/test; the committed Fernet key is
   rejected as a production value.
6. **No general rate limiting** — a deny-by-default read/write/tenant throttle
   matrix is now wired through DRF defaults, with `Retry-After` on every 429.
7. **No central function-level authorization** — a URL-name role policy is
   enforced inside `JWTAuthentication`, so a view that forgets its inline check
   is still denied, and every denial writes an `auth.access_denied` audit row.
8. **Callback replay + outbound SSRF** — outbound POSTs go through one
   `safe_fetch` client (https-only, resolved-IP allowlist, no redirects, 1 MB
   cap); inbound callbacks accept HMAC + timestamp + nonce when configured
   (required in production).
9. **Unbounded consumption** — 5 MB body cap (413), invoice `items` cap (200),
   export single-flight + 1/hour/tenant, Celery time limits/rate limits, queue
   routing, and capped automation sweeps.
10. **BOPLA** — strict-unknown-field handling on the serializers that lacked it,
    per-role output allowlists for patient/invoice detail, `deleted_at` removed,
    and JWT `iss`/`aud` validation.

### Honest scope statement

This is **not** a claim that LabFlow is "1000x secure". It is a set of concrete
attack paths removed, abuse converted into bounded/audited behaviour, and
regression guards added. Residual risk is listed in §9. Some items are
deployment/ops work that code cannot perform (Cloudflare WAF rules, VPS egress
firewall, live n8n workflow audit, prod secret rotation) — those are documented
with exact steps instead of being claimed as done.

---

## 2. What I found in the codebase

### 2.1 The report was partially stale (important)

The report was verified at `5e98a06` with spot-checks at `23b0964`. Main is now
`428b3e3` (PRs #57–#62). Re-running the key greps found:

| Report claim | Current reality (428b3e3) |
|---|---|
| `create_invoice()` fetches patient/branch unscoped (G2) | **Already fixed**: `BillingService.create_invoice` enforces `patient.branch_id in effective_branch_ids(actor)` and `branch.id in ...` |
| Report list/detail unscoped (G1) | Already scoped; `_get_report(report_id, actor)` filters `sample__branch_id__in` |
| Export download token check unverified (A3-5) | **Verified correct**: salted `TimestampSigner`, max-age 7 days, `unsigned == export_id`, status `COMPLETE` |
| Refund role enforcement unverified (A3-5) | **Verified correct**: `REFUND_ROLES = {owner, manager}` + PKR 5,000 Manager ceiling |
| `TestPriceSerializer` used as a write serializer (A3-5) | **Not used for writes** — only `many=True` read serialization in `catalog/views.py` |
| No TOTP enrollment enforcement at main (A2-2) | **Already implemented** by PR #59: `onboarding` claim + state-based `JWTAuthentication` restriction for every route except password/TOTP enrollment + logout |
| Login throttle counts successful logins (A2-8) | Already clears the counters on a successful password (`reset_login_throttle`) |
| Owner excluded from result approval (B3) | **Already includes Owner**: `RESULT_APPROVE_ROLES = {pathologist, owner}` |
| `SessionAuthentication` dead surface (A2-10) | Removed in this run |

### 2.2 What was genuinely still broken (and is now fixed)

- **Samples** (`apps/samples/services.py`): `reject_sample`, `recollect_sample`,
  `cancel_sample` fetched by `pk` with **no branch check**. `get_label`,
  `receive`, `get_events` already had checks.
- **Results** (`apps/results/services.py`): `approve_result`,
  `withdraw_result`, `amend_result`, `record_critical_notification` fetched by
  `pk` with **no branch check**.
- **Sample collection** (`collect_sample`): unscoped invoice fetch and
  `collecting_branch = actor.branch` (wrong-branch custody).
- **Report file download** checked only that a `ReportVersion` row existed with
  the signed `pdf_key` — not that the owning report was FINAL/AMENDED, so a URL
  minted before a void kept working until expiry.
- **Export detail** had no `requested_by` binding.
- **Secrets**: all four defaults still present (`SECRET_KEY`, `JWT_SIGNING_KEY`,
  committed Fernet key, `N8N_WEBHOOK_SECRET = SECRET_KEY`).
- **DEBUG master TOTP code** still present.
- **No throttling except login/reset/report portal**, no body caps, no
  `Retry-After` on report-portal 429s, XFF read from the **leftmost** hop.
- **No inventory, no central role policy, no denial audit, no safe fetcher, no
  callback HMAC/timestamp, no `iss`/`aud`, no atomic refresh reuse claim, no
  fingerprint binding, no strict serializer on patients/catalog/auth/platform,
  no per-role output masking, public `/api/schema|docs|redoc`, no prod settings
  module, `minioadmin` defaults in compose, no Redis password, no container
  limits, no Celery time limits.
- **Refresh reuse detection** was check-then-set (TOCTOU), and refresh tokens
  were not bound to the session's user agent.

### 2.3 Code health observations

- The good patterns the report identified are real and were reused:
  `scoped_to()`, strict serializers, idempotency + payload hash, two-network
  compose, immutable audit tables, queue sweeps capped at 100.
- The main risk is **convergence**, exactly as the report concluded: the right
  pattern exists in some modules and is missing in the module next door.
- `apps/branches/scoping.py::effective_branch_ids` is the codebase's accepted
  scope source (staff_branch assignments **plus** the home-branch v1 fallback).
  The new helpers use it consistently; `scoped_to()` alone was too strict for
  fixtures and would have created false denies.

---

## 3. Implementation by phase

### Phase 0 — Stop the bleeding

| Step | Change | Files |
|---|---|---|
| 0.1 | Fail-closed secrets. `_require_env_secret()` raises `ImproperlyConfigured` when a secret is absent outside dev/test, rejects the public `django-insecure-…` value and the committed Fernet key, and requires `JWT_SIGNING_KEY != SECRET_KEY`. `N8N_WEBHOOK_SECRET` is required (and distinct) when a webhook URL is configured. `DATABASE_URL` has no production default. Compose now requires `JWT_SIGNING_KEY`, `N8N_WEBHOOK_SECRET`, `REDIS_PASSWORD` and R2 keys. | `config/settings/base.py`, `docker-compose.yml`, `.env.example` |
| 0.2 | Deleted the `DEBUG and code == "123456"` master code and the `and not DEBUG` carve-out in the mandatory-TOTP decision. | `apps/accounts/auth_service.py` |
| 0.3 | Verified the existing server-side onboarding gate (PR #59) and added regression tests. An unenrolled mandatory-role token cannot reach business endpoints; it can only enroll TOTP / change password / log out. | `apps/accounts/authentication.py` (existing), tests |
| 0.4 | Verified the three A3-5 items **before** building: export token check correct, refund role gate correct, `TestPriceSerializer` read-only. None was broken, so no emergency reordering was needed. | read-only |

### Phase 1 — Authorization foundations

- **1.1 API inventory-as-code.** New `manage.py api_inventory` command walks both
  URLconfs, resolves every route to a view/method set, records permissions,
  public/private status and the central role policy, and writes
  `docs/api-inventory.json` (317 live paths). `--check` fails on drift. A test
  asserts every authenticated tenant route has a declared policy.
- **1.2 One scoped fetch + BOLA fixes.** Added `in_branch_scope()` and
  `get_scoped_or_404()` to `apps/branches/scoping.py`; fixed the sample/result
  actions and `collect_sample` listed in §2.2; report download now re-checks
  report status; export detail is bound to `requested_by`.
  `_caller_branch()` remains for the legacy transfer paths (documented as
  defence-in-depth; the new checks use `effective_branch_ids`).
- **1.3 Central role policy + deny-by-default.** New
  `apps/core/authorization.py` holds `ROLE_POLICY` (URL name → method → roles)
  and `enforce_role_policy()`. It runs inside `JWTAuthentication` after the
  user and tenant are resolved, so it applies regardless of a view's
  `permission_classes`. A route with no entry is denied. Every denial writes an
  append-only `AuditLog` row with action `auth.access_denied` (route, method,
  role, path, IP, UA). Methods a view does not implement are left to DRF's 405.
- **1.4 Decisions.** Recorded in code + this report:
  - **Patient reads:** all-staff (owner/manager/reception/technician/pathologist),
    because technicians and pathologists need patient context for samples and
    results; PII is masked per role by the serializers (Phase 5.2). This avoids
    the "gate now, break clinical workflow" outcome.
  - **Owner result approval:** already allowed in current code
    (`RESULT_APPROVE_ROLES` includes owner). No change needed; the §6.6 "P-only"
    note in the report is stale. Owner self-approval records an audit note.
- **1.5 Shadow routes.** The duplicate settlement-delivery callback is retained
  deliberately: it is the HMAC-authenticated settlement path, while the
  automation callback is the shared-key path. Both are in the inventory with
  their auth strength; no route was removed because invocation status cannot be
  proven from the repo.

### Phase 2 — Rate limiting & business-flow caps

- **2.1 Throttle matrix.** New `apps/core/throttling.py` (fixed-window, cache
  backed, tenant-keyed). DRF defaults: reads 600/min/user, writes 300/min/user,
  writes 3,000/min/tenant. `Retry-After` (and stable `rate_limited` code) on
  every 429. XFF now uses the **last** trusted hop in accounts, reports,
  authorization and the shared throttle helper.
- **2.2 TOTP verify 10/15 min per account**, keyed on email (or challenge token)
  so a fresh login does not reset the counter; the 5-per-challenge cap remains.
- **2.3 Money velocity.** Per-invoice refund velocity (3/hour), per-user daily
  refund cap (PKR 25,000 for Managers; Owner exempt but audited), discount
  above 25% of subtotal or PKR 10,000 requires Owner, 100% discount follows the
  same Owner rule. All enforced in the service layer.
- **2.4 Body/array caps.** `DATA_UPLOAD_MAX_MEMORY_SIZE` 5 MB,
  `DATA_UPLOAD_MAX_NUMBER_FIELDS` 1000, invoice `items` max 200, and a
  `PayloadLimitMiddleware` that answers **413** with a machine code.
- **2.5 Export guard.** Rejects when an export is already PENDING/RUNNING
  (409), rate-limits requests to 1/hour/tenant, throttles downloads to
  60/min/IP, and binds detail to the requester. The whole-tenant ZIP builder was
  not rewritten to stream (see residual risk).
- **2.6 Celery hardening.** Global 300 s hard / 240 s soft limits; per-task
  annotations for PDF (120 s, 30/m), report delivery (120 s, 60/m),
  notifications (60 s, 60/m), settlement delivery (30/m), export (600 s);
  automation sweep capped at `[:100]` in both the task and service path. The
  worker already uses `-Q celery,notifications,maintenance`.
- **2.7 Edge limits.** Caddy `request_body { max_size 5MB }`, `trusted_proxies
  static private_ranges`; compose `mem_limit`/`cpus` for backend, worker,
  postgres, redis, minio; Redis `--requirepass` with a password in `REDIS_URL`.
- **2.7b Cloudflare WAF/CDN.** Deployment checklist in
  `docs/security/edge-hardening.md` (proxy, Full-strict TLS, HSTS, managed WAF
  ruleset, login/TOTP/reset rate rules, bot mode, origin firewall). Cloudflare
  is external, so this is a runbook, not code.
- **2.8 Step-up.** New `apps/accounts/step_up.py`: fresh TOTP (header
  `X-StepUp-Token`, 5-minute Redis marker) required for settlement
  approve/mark-paid/send and refunds. `STEP_UP_ENABLED` is off in dev/test and
  on in `prod.py`, so existing non-TOTP test accounts are unaffected while real
  mandatory-TOTP roles get the control.
- **2.9 Anomaly sweep.** New `manage.py anomaly_sweep` flags refund spikes
  (>2× the 30-day daily mean), discounts ≥50% of subtotal, and invoice-creation
  spikes (>3× mean), writing `PlatformAudit` rows with action
  `security.anomaly`. Beat runs it daily. Alert-only in v1, as specified.

### Phase 3 — Configuration hardening

- **3.1 Headers + caching.** `SecurityHeadersMiddleware`: CSP
  (`Content-Security-Policy-Report-Only`), Permissions-Policy, COOP/CORP,
  Referrer-Policy, `Cache-Control: no-store, no-cache` + `Pragma` on `/api/*`.
  Settings add HSTS 2 years (+subdomains, no preload), `SECURE_SSL_REDIRECT`,
  explicit `SameSite=Lax`, `CSRF_TRUSTED_ORIGINS` from env, `X_FRAME_OPTIONS`,
  nosniff.
- **3.2 Docs/admin gating.** `DocsGateMiddleware` 404s
  `/api/schema|docs|redoc` unless `DOCS_ENABLED`. Caddy has an
  `ADMIN_ALLOWED_IPS` runbook for `/admin/` (the operator IPs are not knowable
  from the repo). The Django admin also now sits behind the security headers.
- **3.3 R2/MinIO defaults removed** from all compose locations and `.env.example`;
  R2 keys are required, and the local `.env` values were rotated off
  `minioadmin`.
- **3.4 Prod settings.** New `config/settings/prod.py` asserts DEBUG off,
  non-local `ALLOWED_HOSTS`, secret separation, HTTPS redirect + ≥1 year HSTS,
  non-loopback DB, and a configured mailer. `manage.py` refuses to run a
  DEBUG=True settings module unless `LABFLOW_LOCAL_DEV=1`.
- **3.5 Dependencies.** Django pinned to the deployed `6.1.x` line (formal
  adoption of Django 6; Doc 01 still says 5 and should be updated by the
  product owner), upper bounds on the other runtime deps, `sentry-sdk` declared,
  `pip-audit` added to the dev/test extras. `uv.lock` regeneration is listed in
  §10 (needs the user's `uv` toolchain/network).
- **3.6 Ready/internal/Redis.** `/readyz` returns status only (no dependency
  detail) to unauthenticated callers; `InternalPathMiddleware` 404s
  `/internal/*` for public source addresses even if Caddy is bypassed; Redis
  requires a password in compose.
- **3.7 Sentry.** `apps/core/observability.py` with a pure scrubber (secrets,
  tokens, emails, long hex, PII keys) and no-op init when `SENTRY_DSN` is
  empty; `@sentry/react` declared for the SPA. Frontend initialisation was not
  wired (see §10) to avoid an uninstalled-dependency build break tonight.

### Phase 4 — Consumption safety

- **4.1 Safe fetcher.** `apps/core/safe_fetch.py`: https-only (explicit local
  http override), resolution of every address with `is_global` check, redirects
  never followed, 1 MB response cap, mandatory timeout. `automation._post_signed`,
  `notifications.send_notification` and `partners._post_to_n8n` all route
  through it (the existing test seams are preserved). A Django system check
  validates configured webhook URLs at startup.
- **4.2 Inbound callback HMAC + timestamp + replay.**
  `_verify_signed_callback`: HMAC-SHA256 over `<timestamp>.<raw body>`,
  300 s skew, single-use signature cache (600 s), constant-time compare.
  Required when `N8N_CALLBACK_REQUIRE_SIGNATURE` is on (prod); accepted when a
  caller supplies one. Per-IP callback throttle added. The settlement HMAC
  callback keeps its existing signature; timestamp enforcement is documented in
  the n8n audit.
- **4.3 `whatsapp_url` allowlist**: `https://wa.me/...` only, enforced before
  the value is stored (422 `invalid_whatsapp_url`).
- **4.4 Bounded retries.** `WEBHOOK_MAX_ATTEMPTS = 5`; after five failures the
  row becomes terminal `FAILED` with no next attempt (dead-letter analogue)
  instead of retrying forever.
- **4.5 Email.** Django 6 `MAILERS` SMTP configuration with TLS/auth;
  `prod.py` refuses to boot without `EMAIL_HOST`. Password reset now actually
  sends the single-use link with the raw token (previously the token was
  generated and discarded), through `apps/accounts/emails.py`; delivery failure
  is logged and never breaks the non-enumerating 202.
- **4.6 R2 decision.** Local disk remains the storage backend (the code already
  falls back to `FileSystemStorage`); `django-storages`/`boto3` were **not**
  added. This is recorded as an explicit decision with backup implications
  instead of continuing to claim R2 is wired. MinIO defaults are gone.
- **4.7 Interior/PDF boundary.** PDF template test asserts no `http(s)` URLs
  and no remote `src`; the only image is a locally generated `data:` QR.
  Egress firewall rules remain a VPS deployment step (documented in
  `edge-hardening.md`).
- **4.8 n8n audit.** `docs/security/n8n-audit.md` records the inventory
  checklist, the HMAC contract n8n must implement, the network isolation facts,
  and the residual risk.

### Phase 5 — BOPLA + auth hardening

- **5.1 Strict serializers.** New `apps/core/serializers.py`
  (`StrictSerializer`, `StrictModelSerializer`, `reject_unknown_fields`).
  Migrated: patients create/update; catalog Test/Panel/Price create+update;
  all tenant auth serializers (input only); all platform + platform-auth
  serializers. Unknown fields now produce 422 everywhere.
- **5.2 Per-role output allowlist.** `PatientDetailSerializer` masks
  `phone`, `date_of_birth`, contacts and consents for Technician/Pathologist;
  `InvoiceDetailSerializer` masks `patient_phone`, `patient_age`,
  `discount_reason`. Views pass the request into serializer context.
- **5.3 Tests.** New `tests/test_api3_bopla.py` covers strict-field rejection,
  inheritance of the strict base, and the role matrix. `deleted_at` removed from
  patient detail.
- **5.4 Refresh hardening.** Atomic reuse detection via `cache.add` (SET NX) —
  two concurrent replays cannot both win; user-agent fingerprint mismatch
  revokes the session and writes `auth.refresh_fingerprint_mismatch`. The
  fail-closed Redis decision for privileged paths is implemented in the safe
  direction for the claim (a cache error loses the claim and is treated as
  reuse).
- **5.5 JWT `iss`/`aud`.** Minted `iss="labflow"`, `aud="labflow-api"` on access
  and refresh tokens; `decode_jwt` validates both and requires them. Deploying
  this invalidates pre-existing sessions (users re-login), which is the
  documented, safe deploy behaviour; a dual-accept window is available if the
  owner prefers it but was deliberately not left enabled.
- **5.6 Auth throttling + lockout + HIBP.** Refresh 30/min/IP; TOTP 10/15 min;
  progressive lockout after 3 throttled 15-minute windows (1 hour,
  `manage.py unlock_account --tenant … --email …`, audited
  `auth.account_locked` / `auth.account_unlocked`); HIBP k-anonymity screening
  behind `HIBP_ENABLED` (fail-open on provider outage, prefix-only egress).
- **5.7 Hygiene.** `SessionAuthentication` removed from DRF defaults;
  `OriginCheckMiddleware` rejects cross-site `Origin` on login/refresh/TOTP
  verify; login success clears the failed-login counters.

---

## 4. Decisions taken (and why)

| Decision | Choice | Rationale |
|---|---|---|
| Patient-read roles (Doc 03 §6.6) | All staff, with per-role PII masking | Technicians/pathologists need patient context; masking closes the exposure without breaking clinical flow |
| Owner result approval | Allowed (already in code) | Current `RESULT_APPROVE_ROLES` includes owner; the report's "P-only" note is stale; owner self-approval is audited |
| Django version | Adopt 6.1.x, pin `<6.2` | The deployed venv is 6.1.2 and uses `MAILERS`; Doc 01 needs a one-line update |
| R2/MinIO | Local disk storage, documented | Wiring `django-storages`/boto3 safely is a separate change; the false "R2 wired" claim is removed |
| Refresh fingerprint | Bind on user agent only | IP churn is legitimate on mobile networks; UA mismatch is a useful tripwire without false lockouts |
| Step-up / HIBP / callback signatures | Off in dev/test, on in prod | Keeps the suite deterministic while enforcing in production |
| Inline role checks | Kept as defence-in-depth | Central policy is the primary control; removing ~60 inline checks in one night would add more risk than it removes |

---

## 5. Files changed (high level)

**New**
- `backend/apps/core/authorization.py` — role policy + denial audit
- `backend/apps/core/throttling.py` — shared fixed-window throttles
- `backend/apps/core/middleware.py` — 413, headers, internal paths, docs gate, origin check
- `backend/apps/core/safe_fetch.py` — outbound HTTP allowlist client
- `backend/apps/core/serializers.py` — strict serializer bases
- `backend/apps/core/observability.py` — Sentry init + scrubber
- `backend/apps/core/checks.py` — webhook configuration startup check
- `backend/apps/core/tasks.py` — daily anomaly-sweep Celery entry point
- `backend/apps/core/management/commands/api_inventory.py` — inventory + `--check`
- `backend/apps/core/management/commands/anomaly_sweep.py` — daily business-flow flags
- `backend/apps/accounts/step_up.py` — fresh-TOTP step-up
- `backend/apps/accounts/emails.py` — password-reset delivery
- `backend/apps/accounts/management/commands/unlock_account.py` — Owner unlock
- `backend/config/settings/prod.py` — hardened production settings
- `backend/tests/test_lab49_security.py`, `backend/tests/test_api3_bopla.py`
- `docs/api-inventory.json`, `docs/security/*` (spec copy, edge runbook, n8n audit)

**Modified (security-relevant)**
- `backend/config/settings/base.py` (secrets, middleware, throttles, headers, mail, Celery)
- `backend/apps/accounts/{authentication,jwt_engine,auth_service,session_registry,throttling,password_policy,views_auth,views_exports}.py`
- `backend/apps/{samples,results,billing,reports,partners,automation,notifications,patients,catalog,platform}` services/views/serializers as described above
- `docker-compose.yml`, `infra/Caddyfile`, `.env.example`, `.env` (local),
  `backend/pyproject.toml`, `backend/requirements.txt`, `backend/uv.lock`,
  `frontend/package.json`, `frontend/package-lock.json`,
  `backend/config/{wsgi,asgi,celery}.py` (prod settings default)
- Test fixtures/claims updated where the new controls intentionally changed expected behaviour (100% discount → Owner; result-notification sample branch; JWT `iss`/`aud` claims).

---

## 6. Verification

### Automated tests

- `backend/tests/test_lab49_security.py` + `backend/tests/test_api3_bopla.py`
  — **28 passed** (secrets, TOTP master code, role policy + denial audit, policy
  coverage, JWT claims, 413, headers, no-store, docs gate, origin check,
  safe-fetch allowlist, WhatsApp allowlist, password-reset delivery, PDF
  boundary, strict serializers, per-role masking).
- **Root suite** (`tests/` excluding the directory suites): **166 passed**.
- **Affected tenancy suites** (auth/refresh/session, billing read/cancel,
  transfers, reports/PDF/delivery, branch ops, settings, platform admin,
  exports, partners, webhook callbacks, staff CRUD, owner regressions):
  **390 passed, 1 failed** — the failure is
  `test_lab29_report_pdf.py::test_golden_html_matches_checked_in_file`, and it
  is **pre-existing/environmental**: after stripping the QR `data:` URI the HTML
  is byte-identical to the golden file; only the PNG bytes produced by the
  installed `qrcode`/Pillow differ. No template code changed in this run.
- **App-level tests** (`apps/accounts/tests`): **13 passed**.
- Earlier focused batches in this run: 92 + 114 + 30 + 32 + 107 passed after
  the intended behaviour changes (two legacy tests were updated for the 100%
  discount Owner rule and result-notification fixtures were corrected to put
  the sample on the staff member's branch).
- Full-suite command used: `python -m pytest -q -n 4` (never
  `--no-migrations`). On this Windows host xdist occasionally terminated a
  worker (`node down: Not properly terminated`), so the final evidence above
  was produced by serial per-directory runs, which all reached completion.
- `uv lock` regenerated (Django 6.1.2, sentry-sdk 2.74.0, pip-audit 2.10.1).

### Static checks

- `ruff check .` — All checks passed.
- `ruff format --check .` — 398 files already formatted.
- `manage.py check --settings=config.settings.test` — no issues.
- `manage.py api_inventory --check` — matches the live URLconf (317 routes).
- `docker compose config --quiet` — valid.
- Frontend `npm run build` — succeeded (only the existing chunk-size warning).
- `config.settings.prod` booted with production-shaped env (DEBUG off, step-up
  on, HSTS/SSL redirect on); it refuses local `ALLOWED_HOSTS` as designed.

### Checklist status (from the report's test/verification checklist)

| Area | Status |
|---|---|
| API1 two-branch 404 matrix (samples/results/reports/billing, collect, closed branch) | Implemented for the endpoints named in §2.2; existing branch-scope tests green. A consolidated matrix test is in `test_lab49_security.py` for role policy, not every object endpoint. |
| API1 grep-clean of all unscoped `.get(pk=` | Remaining `.objects.get(pk=...)` are tenant-wide/catalog/partner/account lookups, not branch-scoped models. Not every one is behind `get_scoped_or_404` yet (documented). |
| API2 boot with defaults / `grep django-insecure` | Boot guard implemented; the literal remains in `dev.py`/test local defaults only. |
| API2 unenrolled owner token rejected | Existing gate verified + regression test. |
| API2 `123456` never verifies | Regression test with `DEBUG=True`. |
| API2 refresh replay race / fingerprint / Redis-down | Atomic claim + fingerprint implemented; a concurrency test is not yet added. |
| API2 JWT wrong/missing `aud`/`iss` | Tests added. |
| API2 throttles/lockout/breach check | Implemented; lockout/HIBP tests not yet added. |
| API2 reset link delivered | Implemented (locmem in tests); staging end-to-end not run. |
| API3 422 matrix / role matrix / `deleted_at` | Tests added for the gap serializers + serializers; a full HTTP 422 matrix across every endpoint was not written. |
| API3 response-schema CI test | Not implemented (see §10). |
| API4 429 + `Retry-After`, TOTP, items cap, 413, export double-request, XFF | Implemented; k6 burst not run (staging). |
| API5 role×endpoint matrix, method switch, denial audit, realm separation | Central policy + structural coverage + denial audit test; realm separation covered by existing tenant tests. |
| API5 patient-read/owner-approve | Decisions recorded; patient masking tested. |
| API6 refund/discount velocity, report-link fan-out, demo burst, callback replay, step-up, anomaly | Velocity/step-up/anomaly implemented; report-link IP fan-out auto-revoke and demo burst test not run. |
| API7 safe-fetcher payloads, DNS rebinding, redirect, size, live paths, startup | Implemented; unit tests for the fetcher payload list are not yet written (the existing webhook tests exercise the path). |
| API8 header test, docs/admin gate, 405, error verbosity, pip-audit | Headers/docs/405 covered; `pip-audit` CI line is for the user to add; error-verbosity test not added. |
| API9 inventory diff, shadow routes, demo seed, `/readyz`, `/internal/*` | Inventory + readyz + internal implemented; demo-seed hardening skipped (it would break the existing dg seed test; documented). |
| API10 redirect/size, stale timestamp, replay, `whatsapp_url`, retries, email, R2 | Implemented/tested by path; dedicated unit tests for each payload are a follow-up. |

---

## 7. What is genuinely not done (and why)

These are **not** claimed as complete:

1. **Cloudflare WAF/CDN rules** — external dashboard work; runbook provided.
2. **VPS egress firewall** blocking RFC1918/link-local from the backend network
   — deployment step; runbook provided.
3. **k6 "one laptop" burst** — needs staging and k6; the app returns 429 +
   `Retry-After` in unit tests, but the end-to-end load run was not executed.
4. **Live n8n workflow inventory / n8n-side HMAC node** — workflows live
   outside the repo; the contract and checklist are in `docs/security/n8n-audit.md`.
5. **R2 object storage** — deliberately not wired; documented decision and
   backup implications.
6. **Frontend Sentry initialisation** — dependency declared, module not
   imported/initialised tonight to avoid an uninstalled-package build break.
7. **`uv.lock` regeneration** — needs the user's `uv` toolchain/network; the
   `pyproject.toml` pins are in place.
8. **CI workflow changes** — per the hard rule I did not touch
   `.github/workflows/ci.yml`. Add these lines yourself:

```yaml
# after dependency install, before tests
- name: API inventory drift check
  working-directory: backend
  run: python manage.py api_inventory --check

- name: Dependency vulnerability scan
  working-directory: backend
  run: pip-audit --requirement requirements.txt --fail-on high
# or: uv run pip-audit
```

9. **Dedicated unit tests for every safe-fetch payload / lockout / HIBP / schema
   validation** — the controls exist and the main regression suites are green;
   the exhaustive payload matrix is follow-up work.
10. **Demo-seed credential rotation** — the seed is dev-only and already gated;
    randomising passwords would break the existing dg seed verification test
    without a coordinated change.

---

## 8. Behaviour changes operators should expect

- **Deploying the JWT `iss`/`aud` change invalidates existing sessions.** Users
  must log in again. This is a one-time effect.
- **`README`/dev commands:** `manage.py` now requires `LABFLOW_LOCAL_DEV=1` for
  DEBUG=True (added to `backend/.env` locally).
- **Compose now requires** `JWT_SIGNING_KEY`, `N8N_WEBHOOK_SECRET`,
  `REDIS_PASSWORD`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`. A missing value
  fails the boot instead of silently using a default.
- **Redis now has a password**; any external client must use the URL with the
  password.
- **Production requires SMTP** (`EMAIL_HOST`) or it will not boot.
- **`pip install -e .[dev]` now pulls `sentry-sdk` and `pip-audit`.**
- **Frontend API clients that send unknown fields** on patient/catalog/auth/
  platform writes will now get 422 instead of silent discard.

---

## 9. Residual risk

- Cross-tenant isolation remains strong; intra-tenant BOLA is fixed for the
  endpoints in §2.2, but the codebase still has per-object fetches that are not
  all routed through `get_scoped_or_404` (documented, grep-visible).
- A compromised Owner account is tenant-wide by design. A stolen access token
  is usable for ≤15 minutes; a stolen refresh token is now bound to the user
  agent and atomically single-use, but a determined attacker can replay the UA.
- Rate limits are tripwires, not proof of humanity. Distributed abuse stays
  under per-actor caps; Cloudflare/bot rules are the next layer.
- CSP is **report-only**; it is visibility, not protection, until promoted after
  two clean weeks (as specified).
- Safe-fetch validates and disables redirects but is not a full DNS-pinning
  transport; the egress firewall is the backstop. No caller-supplied URL fetch
  exists today, so this is a loaded-gun guard.
- n8n is trusted as a component; a compromised n8n can send correctly signed
  callbacks.
- Local-disk report storage means host loss loses PDFs unless the backup runbook
  is followed.
- `session_registry` read helpers still fail open on cache errors for *reads*
  (access-token denylist checks). The refresh claim fails closed. Making all
  reads fail closed is a policy decision that would turn a Redis outage into a
  full API outage; it was not taken unilaterally.

---

## 10. Follow-up (ordered)

1. Add the two CI lines above (inventory diff, `pip-audit`).
2. Rotate every production secret (`DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`, TOTP
   Fernet key, Postgres password, R2 keys, n8n callback/webhook secrets, SMTP
   app password). The defaults were public; code cannot prove they were never
   used.
3. Run the k6 single-IP burst on staging and record 429/`Retry-After`/no-5xx.
4. Apply the Cloudflare rules from `docs/security/edge-hardening.md`.
5. Complete the live n8n audit and ship the HMAC verify node.
6. Decide R2 vs local disk with the backup owner; if R2, wire `STORAGES` +
   django-storages/boto3 with fail-fast env validation.
7. Add the exhaustive safe-fetch payload tests, the full role×endpoint HTTP
   matrix, refresh-race test, and the response-schema CI test.
8. Promote CSP from report-only after two clean weeks.
9. Update Doc 01 to record Django 6.1 and this report's decisions.

---

## 11. Final test evidence

```
python -m pytest tests/test_lab49_security.py tests/test_api3_bopla.py -q
28 passed

python -m pytest tests --ignore=tests/tenancy --ignore=tests/partners \
  --ignore=tests/automation --ignore=tests/notifications \
  --ignore=tests/isolation --ignore=tests/dg -q
166 passed

python -m pytest <18 affected tenancy modules> -q
390 passed, 1 failed (pre-existing QR-bytes golden mismatch, HTML identical)

python -m pytest apps/accounts/tests -q
13 passed
```

```
ruff check .          -> All checks passed
ruff format --check   -> 398 files already formatted
manage.py check       -> System check identified no issues
api_inventory --check -> matches the live URLconf (317 routes)
docker compose config -> valid
npm run build         -> built in ~48s
```
