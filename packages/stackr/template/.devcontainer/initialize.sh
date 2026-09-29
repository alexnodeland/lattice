#!/usr/bin/env bash
# Runs on the host before the dev container is created. When stackr's stack is running, its
# networks exist: the dev container then joins them, and the application inside it reaches the
# stack's services by name. Otherwise the dev container runs on its own.
set -euo pipefail

cd "$(dirname "$0")"
if docker network inspect stackr >/dev/null 2>&1 &&
  docker network inspect supabase_network_stackr-supabase >/dev/null 2>&1; then
  cat >stackr.generated.yaml <<'YAML'
# Written by initialize.sh: stackr's stack is running.
services:
  dev:
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
      LITELLM_BASE_URL: http://litellm:4000
      LANGFUSE_BASE_URL: http://langfuse-web:3000
      AUTH_JWKS_URL: http://supabase_kong_stackr-supabase:8000/auth/v1/.well-known/jwks.json
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@supabase_db_stackr-supabase:5432/postgres
    networks: [default, stackr, supabase]
networks:
  stackr:
    external: true
  supabase:
    name: supabase_network_stackr-supabase
    external: true
YAML
else
  cat >stackr.generated.yaml <<'YAML'
# Written by initialize.sh: stackr's stack is not running.
services: {}
YAML
fi
