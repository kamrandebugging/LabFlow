# n8n workflow audit (LAB-49 Phase 4.8 / SE-40)

The n8n workflow definitions live outside this repository (`n8n/workflows/` is
empty). This document records the audit procedure and the current mitigation
model. It must be completed against the running n8n instance before production.

## Why this matters

n8n is a second URL-fetching engine in the trust boundary: an HTTP Request node
will fetch any URL its workflow is given, including values derived from a
webhook payload. Django's `apps/core/safe_fetch.py` protects Django's own
outbound calls; it cannot protect n8n's.

## Inventory checklist (run against the live instance)

For every workflow:

| Field | Value |
|---|---|
| Workflow name | |
| Trigger | webhook / schedule / manual |
| HTTP Request nodes | count + every URL expression |
| Callback target | `https://<tenant>.labflow.app/api/v1/webhooks/n8n/...` |
| Credentials used | none / header / credential store |
| Can it reach `internal` services? | should be **no** (edge network only) |

Export the workflows with the n8n CLI (`n8n export:workflow --all --output=...`)
and attach the export to the LAB-49 threat model. Do not commit tenant secrets.

## Known boundaries (verified)

- n8n is attached to the `edge` Compose network only; it cannot resolve
  `postgres`, `redis`, `minio` or `backend` directly (`docker-compose.yml`).
- Caddy is the only public ingress; `/internal/*` is blocked there and again in
  Django (`apps/core/middleware.py::InternalPathMiddleware`).
- Inbound callbacks now accept HMAC-SHA256 over `<timestamp>.<raw body>` with a
  5-minute skew and single-use signature cache when
  `N8N_CALLBACK_REQUIRE_SIGNATURE` is on (production). The static callback key
  remains as a second factor for compatibility.
- `whatsapp_url` is validated at storage time: `https://wa.me/...` only.

## Required n8n-side change

The HMAC verify node must compute:

```
HMAC_SHA256(N8N_CALLBACK_KEY, timestamp + "." + raw_request_body)
```

and send `X-LabFlow-Timestamp` and `X-LabFlow-Signature`. Sign the raw body, not
a re-serialised JSON object. If the signature is absent in production, the
callback is rejected (`401 signature_required`).

## Residual risk

A compromised n8n instance holds the callback key and can still send correctly
signed, well-formed callbacks (recorded as accepted by design). Mitigation:
network isolation, key rotation (`N8N_CALLBACK_KEY_NEXT`), and the bad-signature
alerting hook in the API10 follow-up.
