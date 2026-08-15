#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
available_kib="$(df -Pk "$project_dir" | awk 'NR == 2 {print $4}')"
warning_kib=$((15 * 1024 * 1024))

echo "SD filesystem"
df -h "$project_dir"
echo
echo "FieldLedger directories"
du -sh "$project_dir/backups" "$project_dir/.runtime" 2>/dev/null || true
echo
echo "Docker storage"
docker system df

if (( available_kib < warning_kib )); then
  echo
  echo "WARNING: less than 15 GiB remain on the SD card" >&2
fi
