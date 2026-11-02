# LabFlow: Authoritative Operating Manual & LAB Execution Guide

This document is the **strict, authoritative operating manual** for executing engineering tasks and LAB stories in the **LabFlow** project. Any LLM or developer working on this codebase in ZCode (or any IDE) must adhere to these exact processes, rules, and standards without deviation.

---

## 1. Project Context & Architecture Foundations

- **Product**: LabFlow is a multi-tenant, ISO 15189–compliant clinical laboratory management platform.
- **Backend Stack**: Python 3.12/3.14, Django 6.1, Django REST Framework, `django-tenants` for multi-tenancy.
- **Frontend Stack**: TypeScript, React 18, Vite, Tailwind CSS, Lucide icons, Vitest + Testing Library.
- **Infrastructure Services**: Real Docker containers:
  - `labflow-postgres`: PostgreSQL 16 (strict tenant schema isolation via `django-tenants`).
  - `labflow-redis`: Redis 7 (caching, token denylist, revocation markers).
  - MinIO (S3 object storage), Caddy (TLS reverse proxy).
  - **Zero SQLite shortcuts**: All tests and services run against the real PostgreSQL 16 instance.
- **Python Virtualenv**: Always execute backend commands using the project virtualenv:
  `M:\LabFlow\backend\.venv\Scripts\python.exe` (or `& "M:\LabFlow\backend\.venv\Scripts\python.exe"` in PowerShell).

---

## 2. Core Mandatory Operating Rules

### RULE 1: CI-Green Discipline — Zero Failures on GitHub
**Goal**: When a pull request is opened, CI must pass on the **FIRST run**.
1. **Sync Base First**: Before starting and before final push, fetch and rebase onto `origin/main`.
2. **Replicate All 6 CI Jobs Locally**: Never push until all 6 jobs are 100% green locally.
   - **Job 1 (Lint & Format)**:
     - Backend: `ruff check .`
     - Backend: `ruff format --check .` (Strict 88-char line ceiling)
     - Backend: `mypy .` (Strict type checking, 0 errors across all source files)
     - Frontend: `npx eslint . --max-warnings 0`
     - Frontend: `npx prettier --check .`
   - **Job 2 (Typecheck)**:
     - Frontend: `npm run typecheck` (`tsc --noEmit`)
   - **Job 3 (Unit & Integration Tests)**:
     - Migration Drift: `python manage.py makemigrations --check --dry-run`
     - Backend Pytest: Pytest suite executed against PostgreSQL 16 (`schema_context`)
     - Frontend Vitest: `npm test`
   - **Job 4 (Artifact Build)**:
     - Backend Check: `python manage.py check`
     - Frontend Build: `npm run build`
   - **Job 5 (Secrets Scan)**:
     - Zero committed API keys, tokens, passwords, or `.env` secrets.
   - **Job 6 (Dependency Vulnerabilities)**:
     - Backend: `pip-audit -r backend/requirements.txt` (Zero vulnerabilities)
     - Frontend: `npm audit --audit-level=high` (Zero high/critical vulnerabilities)

### RULE 2: Architecture Specifications (Docs 01–10 Are Authoritative)
- **Tenant Isolation**: Every tenant entity lives in PostgreSQL tenant schemas via `schema_context(tenant.schema_name)` or `tenant_context(tenant)`. Never leak data across schemas.
- **Audit Logging**: Every state-changing mutation (`POST`, `PATCH`, `DELETE`) must write an immutable row to `AuditLog` inside the **same database transaction** (`with transaction.atomic():`). Capture `actor_id`, `action`, `entity_type`, `entity_id`, `before_jsonb`, `after_jsonb`, `ip`, and `user_agent`.
- **Standardized Error Envelopes**: Follow Doc 08 error schema:
  `{"error": {"code": "<string_code>", "message": "<human_readable>", "details": ...}}`
- **Argon2id & Token Security**: Never store raw tokens or passwords. Access tokens (15m expiry), Refresh tokens (24h with rotation and single-use jti denylist).

### RULE 3: Test-Driven Development (TDD) Mandate
- **Test First (RED)**: Write unit, integration, and security verification tests before implementing business logic. Run tests and verify they fail for the intended reason.
- **Implement (GREEN)**: Implement serializers, services, views, and routes to turn the suite green.
- **Definition of Done (DoD) Suite**: Write a dedicated `test_labXX_definition_of_done.py` verifying cross-tenant isolation, RBAC matrices, edge-case constraints, and state audit logs. Minimum 80% test coverage.

### RULE 4: Jira Integration via Terminal (`twg`)
- ZCode does **not** need a GUI Jira extension. Use the terminal CLI `twg` directly:
  - `twg jira workitem get <ISSUE_KEY>`
  - `twg jira workitem transition --id <ISSUE_KEY> --transition-id 21` (In Progress)
  - `twg jira workitem transition --id <ISSUE_KEY> --transition-id 41 --transition-comment "..." --transition-comment-format plain` (In Review)

### RULE 5: Git & Commit Standards
- Dedicated branch: `LAB-<NUMBER>`.
- Commit format (Conventional Commits): `feat(<scope>): <short description> (<JIRA-KEY>)`
- Commit body must enumerate subtask components, validation rules, and testing coverage.
- Push only to `origin/LAB-<NUMBER>` with `--force-with-lease`. Never push directly to `main`.

### RULE 6: Strict Delivery & Full Stop Protocol
- **LAB Branch ONLY**: Commit changes and push strictly to `origin/LAB-<NUMBER>`.
- **Transition Jira**: Move ticket to 'In Review' (Transition ID 41) with structured evidence comment.
- **FULL STOP**: 
  - NO Pull Request creation.
  - NO merging to `main`.
  - NO auto-advancing to the next ticket.
- **Delivery Report**: Output ticket key, branch, tests, coverage %, and list of changed files.
- **Human Gate**: The user reviews code, verifies in the browser, merges manually into `main`, and then says "next".

---

## 3. Coding Style & Quality Guidelines

1. **Strict 88-Character Line Ceiling**: Every Python file must strictly adhere to an 88-character line limit.
2. **Strict Type Annotations**: `mypy .` must pass with zero errors in strict mode.
3. **Immutability (CRITICAL)**: Always return new objects, never mutate in-place.
4. **No Console Logs**: Zero `console.log`, `print()`, or debug code.
5. **Pytest Error Class Gotcha**: Any custom error class whose name starts with `Test` (e.g. `TestNotPricedError`) must declare `__test__ = False`.
6. **Postgres Connection Cleanup**: If pytest hangs on database locks, run:
   `docker exec labflow-postgres psql -U labflow -d postgres -c "DROP DATABASE IF EXISTS test_labflow WITH (FORCE);"`
