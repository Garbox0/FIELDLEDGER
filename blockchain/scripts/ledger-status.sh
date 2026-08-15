#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_dir"

echo "Fabric containers"
docker ps --filter label=service=hyperledger-fabric --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

echo
echo "Gateway and application"
docker ps --filter name=fieldledger --format 'table {{.Names}}\t{{.Status}}'

if [[ -f .env ]] && docker compose ps postgres --status running --quiet | grep -q .; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo
  echo "Ledger outbox"
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT status || ': ' || count(*) FROM ledger_outbox GROUP BY status ORDER BY status;" 2>/dev/null || true
fi
