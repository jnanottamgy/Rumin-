# Common development commands. Each target is a thin wrapper around a command that is
# also documented in README.md, so nothing here is required to work on RUMIN.

BACKEND  := backend
FRONTEND := frontend
UV_RUN   := cd $(BACKEND) && uv run --frozen

.DEFAULT_GOAL := help
.PHONY: help install migrate seed catalog ingest ingest-jobs graph graph-status backend \
        frontend test test-backend test-frontend smoke lint typecheck check openapi \
        api-types verify-models db-up db-down audit deployment-check e2e

help: ## List the available targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

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

graph: ## Build the knowledge graph from the stored data (no network needed)
	$(UV_RUN) python -m app.graph build

graph-status: ## Show the latest graph build and whether its sources changed since
	$(UV_RUN) python -m app.graph status

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

e2e: ## Launch suite: the built app in Chromium on a desktop and a phone (axe, workflows)
	scripts/e2e.sh

deployment-check: ## Build the images and check a throwaway production stack end to end (Docker)
	scripts/deployment_check.sh

GITLEAKS_IMAGE := zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f

audit: ## Known vulnerabilities in the dependencies, and secrets in the git history (network, Docker)
	cd $(BACKEND) && uv export --frozen --all-extras --format requirements-txt --no-emit-project \
		--no-hashes > .audit-requirements.txt && \
		uvx --from pip-audit==2.9.0 pip-audit -r .audit-requirements.txt --disable-pip --no-deps \
		--progress-spinner off; status=$$?; rm -f .audit-requirements.txt; exit $$status
	cd $(FRONTEND) && npm audit --audit-level=high
	docker run --rm -v "$(CURDIR)":/repo -w /repo $(GITLEAKS_IMAGE) git --config /repo/.gitleaks.toml \
		--redact --no-banner .

lint: ## Lint and format checks
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	cd $(FRONTEND) && npm run lint

typecheck: ## Static type checks
	$(UV_RUN) mypy app tests
	cd $(FRONTEND) && npm run typecheck

check: lint typecheck test ## Lint, types and unit tests (CI also runs smoke, e2e, audit, deployment-check)
	$(UV_RUN) python -m app.openapi_export --check

verify-models: ## Run every registered model's verification checks
	$(UV_RUN) python -m app.simulation.verification

openapi: ## Regenerate docs/api/openapi.json from the API
	$(UV_RUN) python -m app.openapi_export

api-types: openapi ## Regenerate the frontend's API types from the contract
	cd $(FRONTEND) && npm run generate:api

db-up: ## Start a local PostgreSQL (docker compose)
	docker compose up -d db

db-down: ## Stop the local PostgreSQL (data is kept in a volume)
	docker compose down
