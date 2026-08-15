.DEFAULT_GOAL := help

.PHONY: help bootstrap up down test migrate seed logs backup config fabric-up gateway-up ledger-up ledger-reconcile ledger-status ledger-smoke storage-status

help:
	@echo "bootstrap  generar .env una sola vez"
	@echo "up         construir e iniciar la base"
	@echo "down       detener contenedores y conservar volúmenes"
	@echo "test       ejecutar pruebas de la API"
	@echo "migrate    aplicar migraciones de base de datos"
	@echo "seed       crear identidades demo idempotentes"
	@echo "logs       seguir logs de servicios"
	@echo "backup     respaldar PostgreSQL y MinIO"
	@echo "config     validar el modelo Compose"
	@echo "fabric-up  iniciar el consorcio Fabric local fijado"
	@echo "gateway-up construir e iniciar el gateway Fabric interno"
	@echo "ledger-up  iniciar Fabric, gateway, API y worker de outbox"
	@echo "ledger-reconcile encolar registros anteriores a Fabric"
	@echo "ledger-status mostrar contenedores Fabric y estado outbox"
	@echo "ledger-smoke probar el flujo real de evidencia API-Fabric"
	@echo "storage-status mostrar uso de SD, backups, runtime y Docker"

bootstrap:
	@./scripts/generate-env.sh

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose build api
	docker compose run --rm --no-deps -e LEDGER_ENABLED=false api pytest -q -p no:cacheprovider

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
