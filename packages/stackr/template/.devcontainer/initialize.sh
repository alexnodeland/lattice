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
    env_file: ../stackr.env
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
