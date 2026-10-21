# LabFlow

Multi-tenant SaaS platform for diagnostic laboratories in Pakistan.

## Architecture & Layout

This repository is organized as a monorepo (Doc 09 §4.1):

```text
labflow/
  backend/            Django 5 + DRF + django-tenants (PostgreSQL schema-per-tenant)
  frontend/           React 18 + TypeScript + Vite + Tailwind CSS SPA
  infra/              Docker Compose, Caddyfile, and deployment scripts
  n8n/workflows/      Self-hosted automation and communication workflows
  docs/               Authoritative engineering specifications (Docs 01–10)
  .github/workflows/  Continuous Integration pipelines
  Makefile            Standard developer interface
  .env.example        Environment variable template
  .editorconfig       Formatting and indentation rules
  .gitignore          Repository hygiene and secret exclusion
```

## Developer Interface

All routine development tasks are invoked via `make` (Doc 09 §16.2):

- `make up`: Start local environment via Docker Compose
- `make down`: Stop local environment
- `make seed`: Populate demo tenant with synthetic fixtures
- `make test`: Run backend and frontend test suites
- `make test-e2e`: Run Playwright end-to-end tests
- `make lint`: Run Ruff, mypy, ESLint, and Prettier checks
- `make types`: Regenerate OpenAPI schemas and TypeScript types
- `make migrate`: Apply database migrations across schemas

## Core Principles

- **No Application Code in Subtask 1:** Repository structure and hygiene only.
- **Zero Secrets Committed:** Credentials exist strictly in host environment files (`.env`).
- **Schema-Per-Tenant Isolation:** Database isolation enforced at the PostgreSQL schema level.

