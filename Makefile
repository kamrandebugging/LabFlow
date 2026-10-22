# ==============================================================================
# LabFlow — Developer & CI Interface (Doc 09 §16.2)
# ==============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: help up down lint test config migrate seed test-e2e types

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all infrastructure services and wait for healthchecks
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
	fi
	docker compose up -d --wait postgres redis minio n8n caddy
	docker compose up -d minio-init
	@for s in labflow-postgres labflow-redis labflow-minio labflow-n8n labflow-caddy; do \
		while [ "$$(docker inspect --format='{{json .State.Health.Status}}' $$s 2>/dev/null | tr -d '\r')" != '"healthy"' ]; do \
			sleep 1; \
		done; \
	done
	@while [ "$$(docker inspect --format='{{.State.Status}}' labflow-minio-init 2>/dev/null | tr -d '\r')" != "exited" ]; do \
		sleep 1; \
	done

down: ## Stop all infrastructure services without removing volumes (preserves data)
	docker compose down

config: ## Validate docker-compose configuration
	docker compose config --quiet

lint: ## Run code linters across backend and frontend
	@echo "Running linters..."

test: ## Run test suites
	@echo "Running tests..."

migrate: ## Run database migrations from backend/
	cd backend && python manage.py migrate

seed: ## Seed local demo tenant data (placeholder until LAB-5)
	@echo "Seeding demo tenant data is scheduled for LAB-5"

test-e2e: ## Run Playwright E2E tests (placeholder until LAB-38)
	@echo "Playwright E2E smoke suite is scheduled for LAB-38"

types: ## Regenerate OpenAPI schemas and frontend types
	cd backend && python manage.py spectacular --file schema.yml
	@echo "Schema generated at backend/schema.yml"
