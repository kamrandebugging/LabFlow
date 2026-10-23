.PHONY: help up down seed test test-e2e lint types migrate

help:
	@echo "LabFlow Developer Interface (Doc 09 §16.2)"
	@echo "  make up        - Start local infrastructure containers"
	@echo "  make down      - Stop local infrastructure containers"
	@echo "  make migrate   - Run shared then tenant schema migrations (Doc 02 §15)"
	@echo "  make seed      - Seed demo tenant and synthetic catalogue"
	@echo "  make test      - Run backend unit and integration test suite"
	@echo "  make test-e2e  - Run Playwright end-to-end tests"
	@echo "  make lint      - Run code style, formatting, and type checks"
	@echo "  make types     - Generate OpenAPI schema and frontend API types"

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd backend && poetry run python manage.py migrate_schemas --shared
	cd backend && poetry run python manage.py migrate_schemas --tenant

seed:
	cd backend && poetry run python manage.py seed_demo_tenant

test:
	cd backend && poetry run pytest

test-e2e:
	cd frontend && npx playwright test

lint:
	cd backend && poetry run ruff check .
	cd backend && poetry run ruff format --check .
	cd backend && poetry run mypy --strict apps/ config/ tests/

types:
	cd backend && poetry run python manage.py spectacular --file schema.yml
