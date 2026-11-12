# Security documentation index (LAB-49)

| Document | Purpose |
|---|---|
| `api-security-10-report.md` | Authoritative OWASP API Top 10 research + implementation spec (copied 2026-11-12) |
| `api-security-10-prompt.md` | The LAB-49 execution prompt / phase contract |
| `lab49-implementation-report.md` | What was found and implemented in this run, decisions, verification, residual risk |
| `edge-hardening.md` | Caddy/Cloudflare WAF, rate limits, container limits, k6 acceptance test |
| `n8n-audit.md` | Live n8n workflow audit checklist + HMAC contract + network isolation facts |

Generated artefacts:

- `docs/api-inventory.json` — canonical route inventory (317 live paths), checked by `python manage.py api_inventory --check`.
- `LAB49_IMPLEMENTATION_REPORT.md` — the same implementation report at the repository root for quick review.
