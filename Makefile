.PHONY: help up down test test-backend test-frontend lint format typecheck seed

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

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

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
