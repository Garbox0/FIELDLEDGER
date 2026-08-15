#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$project_dir/.env"

umask 077
if [[ ! -e "$env_file" ]]; then
  postgres_password="$(openssl rand -hex 32)"
  minio_password="$(openssl rand -hex 32)"
  jwt_secret="$(openssl rand -hex 32)"
  demo_password="$(openssl rand -hex 16)"
  demo_admin_password="$(openssl rand -hex 16)"
  demo_operator_password="$(openssl rand -hex 16)"
  demo_contractor_password="$(openssl rand -hex 16)"
  demo_auditor_password="$(openssl rand -hex 16)"
  demo_viewer_password="$(openssl rand -hex 16)"
  gateway_token="$(openssl rand -hex 32)"

  printf '%s\n' \
    'FIELDLEDGER_PORT=8095' \
    'POSTGRES_DB=fieldledger' \
    'POSTGRES_USER=fieldledger' \
    "POSTGRES_PASSWORD=$postgres_password" \
    'MINIO_ROOT_USER=fieldledger' \
    "MINIO_ROOT_PASSWORD=$minio_password" \
    "JWT_SECRET=$jwt_secret" \
    'JWT_ACCESS_TOKEN_MINUTES=60' \
    "DEMO_PASSWORD=$demo_password" \
    "DEMO_ADMIN_PASSWORD=$demo_admin_password" \
    "DEMO_OPERATOR_PASSWORD=$demo_operator_password" \
    "DEMO_CONTRACTOR_PASSWORD=$demo_contractor_password" \
    "DEMO_AUDITOR_PASSWORD=$demo_auditor_password" \
    "DEMO_VIEWER_PASSWORD=$demo_viewer_password" \
    'PUBLIC_DEMO_VIEWER=false' \
    'TRUSTED_HOSTS=127.0.0.1,localhost,api' \
    'TRUST_CF_CONNECTING_IP=false' \
    'LOGIN_RATE_LIMIT_ATTEMPTS=10' \
    'LOGIN_RATE_LIMIT_WINDOW_SECONDS=60' \
    "INTERNAL_GATEWAY_TOKEN=$gateway_token" \
    'LEDGER_ENABLED=true' \
    > "$env_file"
  echo "Created $env_file with mode 600"
  exit 0
fi

updated=false
if ! grep -q '^JWT_SECRET=' "$env_file"; then
  printf 'JWT_SECRET=%s\n' "$(openssl rand -hex 32)" >> "$env_file"
  updated=true
fi
if ! grep -q '^JWT_ACCESS_TOKEN_MINUTES=' "$env_file"; then
  printf 'JWT_ACCESS_TOKEN_MINUTES=60\n' >> "$env_file"
  updated=true
fi
if ! grep -q '^DEMO_PASSWORD=' "$env_file"; then
  printf 'DEMO_PASSWORD=%s\n' "$(openssl rand -hex 16)" >> "$env_file"
  updated=true
fi
for demo_role in ADMIN OPERATOR CONTRACTOR AUDITOR VIEWER; do
  demo_key="DEMO_${demo_role}_PASSWORD"
  if ! grep -q "^${demo_key}=" "$env_file"; then
    printf '%s=%s\n' "$demo_key" "$(openssl rand -hex 16)" >> "$env_file"
    updated=true
  fi
done
for setting in \
  'PUBLIC_DEMO_VIEWER=false' \
  'TRUSTED_HOSTS=127.0.0.1,localhost,api' \
  'TRUST_CF_CONNECTING_IP=false' \
  'LOGIN_RATE_LIMIT_ATTEMPTS=10' \
  'LOGIN_RATE_LIMIT_WINDOW_SECONDS=60'; do
  setting_key="${setting%%=*}"
  if ! grep -q "^${setting_key}=" "$env_file"; then
    printf '%s\n' "$setting" >> "$env_file"
    updated=true
  fi
done
if ! grep -q '^INTERNAL_GATEWAY_TOKEN=' "$env_file"; then
  printf 'INTERNAL_GATEWAY_TOKEN=%s\n' "$(openssl rand -hex 32)" >> "$env_file"
  updated=true
fi
if ! grep -q '^LEDGER_ENABLED=' "$env_file"; then
  printf 'LEDGER_ENABLED=true\n' >> "$env_file"
  updated=true
fi
chmod 600 "$env_file"

if [[ "$updated" == true ]]; then
  echo "Added missing application secrets to the existing .env"
else
  echo ".env already contains all required settings; leaving values unchanged"
fi
