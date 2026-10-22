# ==============================================================================
# LabFlow — Developer & CI Interface (Doc 09 §16.2)
# ==============================================================================

.PHONY: help up down lint test migrate seed test-e2e types

# Shows available make targets and descriptions
help:
	@echo "LabFlow Developer Interface:"
	@echo "  make up       - Starts backend and frontend dev servers locally"
	@echo "  make down     - Stops local dev servers"
	@echo "  make lint     - Runs backend (ruff + mypy) and frontend (lint + format + typecheck)"
	@echo "  make test     - Runs backend pytest and frontend test/typecheck"
	@echo "  make migrate  - Runs database migrations from backend/"
	@echo "  make seed     - Seeds local demo tenant data"
	@echo "  make test-e2e - Runs Playwright E2E tests"
	@echo "  make types    - Regenerates OpenAPI schemas and frontend types"

# Starts the backend dev server and the frontend Vite dev server locally
up:
	@echo "Starting backend (port 8000) and frontend (port 5173)..."
	(cd backend && python manage.py runserver) & (cd frontend && npm run dev)

# Stops locally running dev servers
down:
	@echo "Stopping local development servers..."
	@-pkill -f "manage.py runserver" 2>/dev/null || true
	@-pkill -f "vite" 2>/dev/null || true

# Runs backend ruff + mypy (Subtask 3) and frontend lint + format:check + typecheck (Subtask 5) and fails if any one fails
lint:
	cd backend && ruff check .
	cd backend && ruff format --check .
	cd backend && mypy config tests
	cd frontend && npm run lint
	cd frontend && npm run format:check
	cd frontend && npm run typecheck

# Runs backend pytest (Subtask 3) and the frontend test/typecheck step on the empty scaffolds
test:
	cd backend && pytest
	cd frontend && npm run typecheck

# Runs python manage.py migrate from backend/
migrate:
	cd backend && python manage.py migrate

# Seeds local demo tenant data (placeholder until LAB-5)
seed:
	@echo "Seeding demo tenant data is scheduled for LAB-5"

# Runs Playwright E2E smoke tests (placeholder until LAB-38)
test-e2e:
	@echo "Playwright E2E smoke suite is scheduled for LAB-38"

# Regenerates OpenAPI schema and frontend TypeScript types (Doc 09 §6.1, §8.3)
types:
	cd backend && python manage.py spectacular --file schema.yml
	@echo "Schema generated at backend/schema.yml"
