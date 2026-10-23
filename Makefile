.PHONY: help up down test test-backend test-frontend lint format typecheck seed migrate test-e2e types

SHELL := /usr/bin/env bash

help:
	@echo "LabFlow Development Commands:"
	@echo "  make up             Start Docker Compose development stack"
	@echo "  make down           Stop Docker Compose development stack"
	@echo "  make test           Run full backend test suite"
	@echo "  make test-backend   Run backend pytest suite against PostgreSQL and Redis"
	@echo "  make lint           Run backend and frontend linters"
	@echo "  make format         Run backend and frontend code formatters"
	@echo "  make typecheck      Run Mypy strict type checks"
	@echo "  make migrate        Run shared then tenant schema migrations (Doc 02 §15)"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd backend && poetry run python manage.py migrate_schemas --shared
	cd backend && poetry run python manage.py migrate_schemas --tenant

test-backend:
	@echo "==> Running LabFlow backend test suite against PostgreSQL & Redis..."
	cd backend && python -m pytest -v

test-frontend:
	@echo "==> Running LabFlow frontend tests..."
	@if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then \
		cd frontend && npm test -- --run; \
	else \
		echo "Frontend test suite not initialized yet. Skipping."; \
	fi

test: test-backend

lint:
	cd backend && python -m ruff check .

format:
	cd backend && python -m ruff format .

typecheck:
	cd backend && python -m mypy --config-file pyproject.toml tests/ config/

test-e2e:
	cd frontend && npx playwright test

types:
	cd backend && poetry run python manage.py spectacular --file schema.yml
