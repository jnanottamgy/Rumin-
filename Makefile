# Common development commands. Each target is a thin wrapper around a command that is
# also documented in README.md, so nothing here is required to work on RUMIN.

BACKEND  := backend
FRONTEND := frontend
UV_RUN   := cd $(BACKEND) && uv run --frozen

.DEFAULT_GOAL := help
.PHONY: help install migrate seed catalog ingest ingest-jobs backend frontend test test-backend \
        test-frontend smoke lint typecheck check openapi api-types db-up db-down

help: ## List the available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies
	cd $(BACKEND) && uv sync --frozen --extra dev
	cd $(FRONTEND) && npm ci

migrate: ## Apply database migrations
	$(UV_RUN) alembic upgrade head

seed: ## Load the illustrative sample dataset (idempotent)
	$(UV_RUN) python -m app.db.seed

catalog: ## Load the series catalogue (definitions only; fetches nothing)
	$(UV_RUN) python -m app.ingestion catalog

ingest: ## Retrieve the World Bank series (needs internet access to api.worldbank.org)
	$(UV_RUN) python -m app.ingestion run worldbank-wdi

ingest-jobs: ## List recent ingestion runs
	$(UV_RUN) python -m app.ingestion jobs

backend: ## Run the API with auto-reload on http://127.0.0.1:8000
	$(UV_RUN) uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend: ## Run the web client on http://127.0.0.1:5173
	cd $(FRONTEND) && npm run dev -- --host 127.0.0.1

test: test-backend test-frontend ## Run all unit and API tests

test-backend: ## Backend tests (pytest)
	$(UV_RUN) pytest

test-frontend: ## Frontend tests (Vitest)
	cd $(FRONTEND) && npm test

smoke: ## End-to-end: fresh database, live API, frontend integration suite
	scripts/smoke_test.sh

lint: ## Lint and format checks
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	cd $(FRONTEND) && npm run lint

typecheck: ## Static type checks
	$(UV_RUN) mypy app tests
	cd $(FRONTEND) && npm run typecheck

check: lint typecheck test ## Everything CI runs except the smoke test
	$(UV_RUN) python -m app.openapi_export --check

openapi: ## Regenerate docs/api/openapi.json from the API
	$(UV_RUN) python -m app.openapi_export

api-types: openapi ## Regenerate the frontend's API types from the contract
	cd $(FRONTEND) && npm run generate:api

db-up: ## Start a local PostgreSQL (docker compose)
	docker compose up -d db

db-down: ## Stop the local PostgreSQL (data is kept in a volume)
	docker compose down
