.PHONY: help install dev-db migrate api worker web test lint typecheck demo docker-up docker-down

BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend (uv) and frontend (pnpm) dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && pnpm install

dev-db:  ## Create local Postgres databases for development and tests
	createdb rm_dev || true
	createdb rm_test || true

migrate:  ## Apply database migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

api:  ## Run the API with auto-reload on :8000
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

worker:  ## Run the background worker (imports and reports)
	cd $(BACKEND) && .venv/bin/celery -A app.workers.celery_app worker --loglevel=info --pool threads --concurrency 4

web:  ## Run the web UI with hot reload on :5173
	cd $(FRONTEND) && pnpm dev

demo:  ## Load demo networks and four months of synthetic scans
	cd $(BACKEND) && .venv/bin/python -m app.cli seed-demo

test:  ## Run backend tests
	cd $(BACKEND) && .venv/bin/pytest

lint:  ## Lint backend and frontend
	cd $(BACKEND) && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
	cd $(FRONTEND) && pnpm lint

typecheck:  ## Type-check backend and frontend
	cd $(BACKEND) && .venv/bin/mypy app
	cd $(FRONTEND) && pnpm exec tsc --noEmit

docker-up:  ## Build and start the production stack
	docker compose -f deploy/docker-compose.yml --env-file .env up -d --build

docker-down:  ## Stop the production stack
	docker compose -f deploy/docker-compose.yml --env-file .env down
