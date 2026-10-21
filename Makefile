# ==============================================================================
# LabFlow — Root Developer Interface (Doc 09 §16.2)
# ==============================================================================

.PHONY: help up down seed test test-e2e lint types migrate

help:
	@echo "LabFlow Developer Commands:"
	@echo "  make up        - Start full local stack via Docker Compose"
	@echo "  make down      - Stop full local stack"
	@echo "  make seed      - Rebuild demo tenant with synthetic data"
	@echo "  make test      - Run backend & frontend unit/API test suites"
	@echo "  make test-e2e  - Run Playwright E2E smoke tests"
	@echo "  make lint      - Run linters (Ruff, mypy, ESLint, Prettier)"
	@echo "  make types     - Regenerate OpenAPI schema and TS types"
	@echo "  make migrate   - Apply migrations to all schemas"

up:
	@echo "Starting containers... (implemented in LAB-2)"

down:
	@echo "Stopping containers... (implemented in LAB-2)"

seed:
	@echo "Seeding demo tenant... (implemented in later subtask)"

test:
	@echo "Running tests... (implemented in later subtask)"

test-e2e:
	@echo "Running E2E tests... (implemented in later subtask)"

lint:
	@echo "Running linters... (implemented in later subtask)"

types:
	@echo "Generating types... (implemented in later subtask)"

migrate:
	@echo "Running migrations... (implemented in later subtask)"

