.DEFAULT_GOAL := help

.PHONY: help bootstrap up down test migrate seed logs backup config fabric-up gateway-up ledger-up ledger-reconcile ledger-status ledger-smoke storage-status

help:
	@echo "bootstrap  generate .env once"
	@echo "up         build and start the foundation"
	@echo "down       stop containers; keep volumes"
	@echo "test       run API tests"
	@echo "migrate    apply database migrations"
	@echo "seed       create idempotent demo identities"
	@echo "logs       follow service logs"
	@echo "backup     back up PostgreSQL and MinIO"
	@echo "config     validate the Compose model"
	@echo "fabric-up  bootstrap the pinned local Fabric consortium"
	@echo "gateway-up build and start the internal Fabric gateway"
	@echo "ledger-up  start Fabric, gateway, API, and outbox worker"
	@echo "ledger-reconcile enqueue pre-Fabric records"
	@echo "ledger-status show Fabric containers and outbox state"
	@echo "ledger-smoke exercise the live API-to-Fabric evidence flow"
	@echo "storage-status show SD, backup, runtime, and Docker use"

bootstrap:
	@./scripts/generate-env.sh

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose build api
	docker compose run --rm --no-deps api pytest -q -p no:cacheprovider

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m app.seed

logs:
	docker compose logs -f --tail=100

backup:
	@./scripts/backup.sh

config:
	docker compose config --quiet

fabric-up:
	@./blockchain/scripts/fabric-up.sh

gateway-up:
	docker compose --env-file .env -f services/fabric-gateway/docker-compose.yml up -d --build

ledger-up: fabric-up gateway-up migrate
	docker compose up -d --build

ledger-reconcile:
	docker compose run --rm api python -m app.reconcile_ledger

ledger-status:
	@./blockchain/scripts/ledger-status.sh

ledger-smoke:
	docker compose run --rm api python -m app.e2e_ledger_smoke

storage-status:
	@./scripts/storage-status.sh
