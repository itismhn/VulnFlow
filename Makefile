.PHONY: help install dev-db migrate api worker web test lint typecheck demo \
	docker-env docker-up docker-down docker-ps docker-logs docker-admin docker-demo docker-backup docker-bundle

BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin
COMPOSE := docker compose -f deploy/docker-compose.yml --env-file .env
BUNDLE := dist/vulnflow-offline
PLATFORM ?= linux/amd64
IMAGES := vulnflow-api:latest vulnflow-web:latest postgres:17-alpine redis:7-alpine

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend (uv) and frontend (pnpm) dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && pnpm install

dev-db:  ## Create local Postgres databases for development and tests
	createdb rm_dev || true
	createdb rm_test || true

migrate:  ## Apply database migrations and create the default admin on a fresh install
	cd $(BACKEND) && .venv/bin/alembic upgrade head && .venv/bin/python -m app.cli ensure-admin

api:  ## Run the API with auto-reload on :8000
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

worker:  ## Run the background worker (imports and reports)
	cd $(BACKEND) && .venv/bin/celery -A app.workers.celery_app worker --beat --schedule /tmp/rm-celerybeat-schedule --loglevel=info --pool threads --concurrency 4

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

docker-env:  ## Create .env with random secrets (for plain-http trial use)
	@test ! -f .env || { echo ".env already exists, not overwriting"; exit 1; }
	sed -e "s/^RM_SECRET_KEY=.*/RM_SECRET_KEY=$$(openssl rand -hex 48)/" \
		-e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 24)/" \
		-e "s/^RM_COOKIE_SECURE=.*/RM_COOKIE_SECURE=false/" \
		.env.example > .env
	@echo "Wrote .env. RM_COOKIE_SECURE=false: set it to true once you serve over HTTPS."

docker-up:  ## Build and start the production stack
	$(COMPOSE) up -d --build

docker-down:  ## Stop the production stack (data volumes are kept)
	$(COMPOSE) down

docker-ps:  ## Show container status
	$(COMPOSE) ps

docker-logs:  ## Follow logs of all containers
	$(COMPOSE) logs -f --tail=100

docker-admin:  ## Create the first admin account in the Docker stack
	$(COMPOSE) exec api python -m app.cli create-admin

docker-demo:  ## Load demo data into the Docker stack
	$(COMPOSE) exec api python -m app.cli seed-demo

docker-backup:  ## Dump the database to backups/ (uploaded files live in the storage volume)
	@mkdir -p backups
	$(COMPOSE) exec -T db pg_dump -U report_manager -Fc report_manager > backups/vulnflow-$$(date +%Y%m%d-%H%M%S).dump
	@ls -lh backups | tail -1

docker-bundle:  ## Build images for a host without internet into dist/vulnflow-offline.zip (PLATFORM=linux/amd64)
	rm -rf $(BUNDLE) dist/vulnflow-offline.zip && mkdir -p $(BUNDLE)/deploy
	docker build --platform $(PLATFORM) -t vulnflow-api:latest $(BACKEND)
	docker build --platform $(PLATFORM) -t vulnflow-web:latest $(FRONTEND)
	docker pull --platform $(PLATFORM) postgres:17-alpine
	docker pull --platform $(PLATFORM) redis:7-alpine
	docker save --platform $(PLATFORM) -o $(BUNDLE)/vulnflow-images.tar $(IMAGES)
	@# The offline host has no source tree, so it runs the prebuilt images only
	grep -v '^ *build: ' deploy/docker-compose.yml > $(BUNDLE)/deploy/docker-compose.yml
	cp .env.example README.md $(BUNDLE)/
	cd dist && zip -qr vulnflow-offline.zip vulnflow-offline
	@ls -lh dist/vulnflow-offline.zip
