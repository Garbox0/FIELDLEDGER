#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_dir="$project_dir/backups"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "$project_dir/.env" ]]; then
  echo "Missing .env; run make bootstrap first" >&2
  exit 1
fi

set -a
source "$project_dir/.env"
set +a

available_kib="$(df -Pk "$project_dir" | awk 'NR == 2 {print $4}')"
reserve_kib=$((10 * 1024 * 1024))
database_bytes="$(docker compose exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT pg_database_size(current_database());")"
minio_kib="$(docker run --rm \
  --volume fieldledger_minio-data:/source:ro \
  postgres:18.4-bookworm du -sk /source | awk '{print $1}')"
database_kib=$(((database_bytes + 1023) / 1024))
estimated_backup_kib=$(((database_kib + minio_kib) * 2))
required_kib=$((reserve_kib + estimated_backup_kib))
if (( available_kib < required_kib )); then
  echo "Backup refused: it could reduce SD free space below the 10 GiB reserve" >&2
  exit 1
fi
mkdir -p "$backup_dir"

cd "$project_dir"
docker compose exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip > "$backup_dir/postgres-$timestamp.sql.gz"

# A short stop makes the raw object-store volume snapshot consistent.
docker compose stop minio >/dev/null
trap 'docker compose start minio >/dev/null' EXIT
docker run --rm \
  --volume fieldledger_minio-data:/source:ro \
  postgres:18.4-bookworm \
  tar -C /source -czf - . > "$backup_dir/minio-$timestamp.tar.gz"
docker compose start minio >/dev/null
trap - EXIT

manifest="$backup_dir/backup-$timestamp.sha256"
(
  cd "$backup_dir"
  sha256sum "postgres-$timestamp.sql.gz" "minio-$timestamp.tar.gz" > "$(basename "$manifest")"
)

echo "Backup created in $backup_dir"
