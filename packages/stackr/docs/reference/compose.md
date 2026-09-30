# Compose services and profiles

`compose.yaml` is one Compose project, `stackr`, whose services are grouped in profiles ([The stack and its profiles](../guides/stack.md)). Local Supabase isn't in it: its CLI runs it beside the project ([Local Supabase](../guides/supabase.md)).

## Profiles

<!-- generated: compose-profiles -->

| Profile | Services | In `make up`'s default |
|---|---|---|
| `observability` | `otel-collector`, `tempo`, `prometheus`, `loki`, `pyroscope`, `grafana` | yes |
| `postgres` | `postgres` | no |
| `langfuse` | `db-init`, `redis`, `minio`, `clickhouse`, `langfuse-worker`, `langfuse-web` | yes |
| `gateway` | `db-init`, `redis`, `litellm` | yes |
| `smoke` | `telemetrygen` | no |

<!-- end generated -->

`make up PROFILES="..."` chooses others. `postgres` is added by `make up` when `STACKR_DATABASE=postgres` and a profile needs a database; `smoke` holds `telemetrygen`, which `scripts/smoke` runs once per signal.

## Networks

<!-- generated: compose-networks -->

| Network | Created | Joined by |
|---|---|---|
| `stackr` | by Compose | `otel-collector`, `tempo`, `prometheus`, `loki`, `pyroscope`, `grafana`, `postgres`, `db-init`, `redis`, `minio`, `clickhouse`, `langfuse-worker`, `langfuse-web`, `litellm`, `telemetrygen` |
| `supabase_network_stackr-supabase` | by `make up`, if missing | `db-init`, `langfuse-worker`, `langfuse-web`, `litellm` |

<!-- end generated -->

## Volumes

`make down` keeps these, and `make reset` deletes them.

<!-- generated: compose-volumes -->

| Volume | Mounted by |
|---|---|
| `prometheus-data` | `prometheus` at `/prometheus` |
| `tempo-data` | `tempo` at `/var/tempo` |
| `loki-data` | `loki` at `/loki` |
| `pyroscope-data` | `pyroscope` at `/data` |
| `grafana-data` | `grafana` at `/var/lib/grafana` |
| `postgres-data` | `postgres` at `/var/lib/postgresql/data` |
| `redis-data` | `redis` at `/data` |
| `minio-data` | `minio` at `/data` |
| `clickhouse-data` | `clickhouse` at `/var/lib/clickhouse` |
| `clickhouse-logs` | `clickhouse` at `/var/log/clickhouse-server` |

<!-- end generated -->

## Services

Published ports are shown as the host port, with the setting in `.env` that changes it, and the port inside the container. Every published port binds to `STACKR_BIND`, `127.0.0.1` by default. Values such as `${NAME:?run make env}` come from `.env`, and Compose refuses to start without them; `${NAME:-default}` falls back to its default.

<!-- generated: compose-services -->

### `otel-collector`

The telemetry port. Receives OTLP from applications and the gateway, and exports each signal to its backend.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `otel/opentelemetry-collector-contrib`, pinned by tag in `compose.yaml` |
| Published ports | 4317 (`OTLP_GRPC_PORT`) → 4317, 4318 (`OTLP_HTTP_PORT`) → 4318 |
| Networks | `stackr` |
| Volumes | `./deploy/otel-collector/config.yaml` → `/etc/otelcol-contrib/config.yaml` (read-only) |
| Depends on | `tempo`, `prometheus`, `loki` |
| Runs | `--config=/etc/otelcol-contrib/config.yaml` |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `STACKR_ENVIRONMENT` | `${STACKR_ENVIRONMENT:-local}` |
    | `STACKR_TRACES_EXPORTERS` | `${STACKR_TRACES_EXPORTERS:-[otlp_grpc/tempo, otlp_http/langfuse]}` |
    | `LANGFUSE_OTLP_AUTH` | `${LANGFUSE_OTLP_AUTH:?run make env}` |

### `tempo`

Traces, with its metrics generator for span metrics and service graphs.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `grafana/tempo`, pinned by tag in `compose.yaml` |
| Published ports | 3200 (`TEMPO_PORT`) → 3200 |
| Networks | `stackr` |
| Volumes | `./deploy/tempo/tempo.yaml` → `/etc/tempo/tempo.yaml` (read-only), `tempo-data` → `/var/tempo` |
| Depends on | `prometheus` |
| Runs | `-config.file=/etc/tempo/tempo.yaml` |
| Restart | `unless-stopped` |

### `prometheus`

Metrics: OTLP from the Collector, remote write from Tempo, and scrapes of the stack's own services.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `prom/prometheus`, pinned by tag in `compose.yaml` |
| Published ports | 9090 (`PROMETHEUS_PORT`) → 9090 |
| Networks | `stackr` |
| Volumes | `./deploy/prometheus/prometheus.yml` → `/etc/prometheus/prometheus.yml` (read-only), `prometheus-data` → `/prometheus` |
| Depends on | none |
| Runs | `--config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --storage.tsdb.retention.time=15d --web.enable-otlp-receiver --web.enable-remote-write-receiver --enable-feature=exemplar-storage` |
| Health check | `wget -q -O /dev/null http://127.0.0.1:9090/-/ready`, every 5s |
| Restart | `unless-stopped` |

### `loki`

Logs, over OTLP.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `grafana/loki`, pinned by tag in `compose.yaml` |
| Published ports | 3100 (`LOKI_PORT`) → 3100 |
| Networks | `stackr` |
| Volumes | `./deploy/loki/loki.yaml` → `/etc/loki/loki.yaml` (read-only), `loki-data` → `/loki` |
| Depends on | none |
| Runs | `-config.file=/etc/loki/loki.yaml` |
| Restart | `unless-stopped` |

### `pyroscope`

Profiles, pushed by applications.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `grafana/pyroscope`, pinned by tag in `compose.yaml` |
| Published ports | 4040 (`PYROSCOPE_PORT`) → 4040 |
| Networks | `stackr` |
| Volumes | `./deploy/pyroscope/config.yaml` → `/etc/pyroscope/config.yaml` (read-only), `pyroscope-data` → `/data` |
| Depends on | none |
| Runs | `-config.file=/etc/pyroscope/config.yaml` |
| Restart | `unless-stopped` |

### `grafana`

Dashboards and exploration, over the four backends.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `grafana/grafana`, pinned by tag in `compose.yaml` |
| Published ports | 3000 (`GRAFANA_PORT`) → 3000 |
| Networks | `stackr` |
| Volumes | `./deploy/grafana/provisioning/datasources` → `/etc/grafana/provisioning/datasources` (read-only), `./deploy/grafana/provisioning/dashboards` → `/etc/grafana/provisioning/dashboards` (read-only), `./deploy/grafana/dashboards/stackr` → `/var/lib/grafana/dashboards/stackr` (read-only), `../artifactr/deploy/grafana/dashboards` → `/var/lib/grafana/dashboards/artifactr` (read-only), `../reflexr/deploy/grafana/dashboards` → `/var/lib/grafana/dashboards/reflexr` (read-only), `grafana-data` → `/var/lib/grafana` |
| Depends on | `prometheus`, `tempo`, `loki`, `pyroscope` |
| Health check | `wget -q -O /dev/null http://127.0.0.1:3000/api/health`, every 5s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `GF_SECURITY_ADMIN_USER` | `admin` |
    | `GF_SECURITY_ADMIN_PASSWORD` | `${GRAFANA_ADMIN_PASSWORD:?run make env}` |
    | `GF_ANALYTICS_REPORTING_ENABLED` | `false` |
    | `GF_ANALYTICS_CHECK_FOR_UPDATES` | `false` |
    | `GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES` | `false` |
    | `GF_NEWS_NEWS_FEED_ENABLED` | `false` |

### `postgres`

Plain PostgreSQL, the alternative database adapter, used when STACKR_DATABASE is `postgres`.

| Property | Value |
|---|---|
| Profiles | `postgres` |
| Image | `postgres`, pinned by tag in `compose.yaml` |
| Published ports | 55432 (`POSTGRES_PORT`) → 5432 |
| Networks | `stackr` |
| Volumes | `postgres-data` → `/var/lib/postgresql/data` |
| Depends on | none |
| Health check | `pg_isready -U "$POSTGRES_USER" -d postgres`, every 3s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `POSTGRES_USER` | `postgres` |
    | `POSTGRES_PASSWORD` | `${POSTGRES_ADMIN_PASSWORD:?run make env}` |
    | `TZ` | `UTC` |
    | `PGTZ` | `UTC` |

### `db-init`

Creates each service's role and database on the database adapter, on every start, then exits.

| Property | Value |
|---|---|
| Profiles | `langfuse`, `gateway` |
| Image | `postgres`, pinned by tag in `compose.yaml` |
| Published ports | none |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | `./deploy/postgres/init.sql` → `/init.sql` (read-only) |
| Depends on | `postgres` (healthy, when it runs) |
| Runs | `psql --no-psqlrc --quiet --file=/init.sql` |
| Restart | `no` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `PGHOST` | `${STACKR_DB_HOST:-supabase_db_stackr-supabase}` |
    | `PGPORT` | `5432` |
    | `PGDATABASE` | `postgres` |
    | `PGUSER` | `postgres` |
    | `PGPASSWORD` | `${STACKR_DB_ADMIN_PASSWORD:-postgres}` |
    | `PGCONNECT_TIMEOUT` | `10` |
    | `LANGFUSE_DB_PASSWORD` | `${LANGFUSE_DB_PASSWORD:?run make env}` |
    | `LITELLM_DB_PASSWORD` | `${LITELLM_DB_PASSWORD:?run make env}` |

### `redis`

Valkey, for the Redis protocol: Langfuse's queues and cache in database 0, the gateway's routing state and cache in database 1.

| Property | Value |
|---|---|
| Profiles | `langfuse`, `gateway` |
| Image | `valkey/valkey`, pinned by tag in `compose.yaml` |
| Published ports | none |
| Networks | `stackr` |
| Volumes | `redis-data` → `/data` |
| Depends on | none |
| Runs | `sh -c printf 'requirepass %s\n' "$REDIS_PASSWORD" > /tmp/valkey.conf && exec valkey-server /tmp/valkey.conf --maxmemory-policy noeviction --save 60 1` |
| Health check | `valkey-cli ping`, every 3s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `REDIS_PASSWORD` | `${REDIS_PASSWORD:?run make env}` |
    | `REDISCLI_AUTH` | `${REDIS_PASSWORD:?run make env}` |

### `minio`

MinIO, for the S3 port: Langfuse's event and media bucket, `langfuse`.

| Property | Value |
|---|---|
| Profiles | `langfuse` |
| Image | `cgr.dev/chainguard/minio`, pinned by tag and digest in `compose.yaml` |
| Published ports | 9000 (`MINIO_PORT`) → 9000, 9001 (`MINIO_CONSOLE_PORT`) → 9001 |
| Networks | `stackr` |
| Volumes | `minio-data` → `/data` |
| Depends on | none |
| Runs | `sh -c mkdir -p /data/langfuse && exec minio server --address :9000 --console-address :9001 /data` |
| Health check | `mc ready local`, every 3s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `MINIO_ROOT_USER` | `${S3_ACCESS_KEY_ID:-stackr}` |
    | `MINIO_ROOT_PASSWORD` | `${S3_SECRET_ACCESS_KEY:?run make env}` |

### `clickhouse`

Langfuse's traces, observations and scores.

| Property | Value |
|---|---|
| Profiles | `langfuse` |
| Image | `clickhouse/clickhouse-server`, pinned by tag in `compose.yaml` |
| Published ports | none |
| Networks | `stackr` |
| Volumes | `clickhouse-data` → `/var/lib/clickhouse`, `clickhouse-logs` → `/var/log/clickhouse-server` |
| Depends on | none |
| Health check | `wget --no-verbose --tries=1 --spider http://127.0.0.1:8123/ping`, every 3s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `CLICKHOUSE_DB` | `default` |
    | `CLICKHOUSE_USER` | `langfuse` |
    | `CLICKHOUSE_PASSWORD` | `${CLICKHOUSE_PASSWORD:?run make env}` |

### `langfuse-worker`

Langfuse's worker: runs ingestion and evaluation jobs from the queues.

| Property | Value |
|---|---|
| Profiles | `langfuse` |
| Image | `langfuse/langfuse-worker`, pinned by tag in `compose.yaml` |
| Published ports | none |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | none |
| Depends on | `db-init` (completed), `redis` (healthy), `minio` (healthy), `clickhouse` (healthy) |
| Health check | `wget -q -O /dev/null http://127.0.0.1:3030/api/health`, every 5s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `DATABASE_URL` | `postgresql://langfuse:${LANGFUSE_DB_PASSWORD:?run make env}@${STACKR_DB_HOST:-supabase_db_stackr-supabase}:5432/langfuse` |
    | `SALT` | `${LANGFUSE_SALT:?run make env}` |
    | `ENCRYPTION_KEY` | `${LANGFUSE_ENCRYPTION_KEY:?run make env}` |
    | `NEXTAUTH_URL` | `http://localhost:${LANGFUSE_PORT:-3300}` |
    | `TELEMETRY_ENABLED` | `false` |
    | `HOSTNAME` | `0.0.0.0` |
    | `CLICKHOUSE_URL` | `http://clickhouse:8123` |
    | `CLICKHOUSE_MIGRATION_URL` | `clickhouse://clickhouse:9000` |
    | `CLICKHOUSE_USER` | `langfuse` |
    | `CLICKHOUSE_PASSWORD` | `${CLICKHOUSE_PASSWORD:?run make env}` |
    | `CLICKHOUSE_CLUSTER_ENABLED` | `false` |
    | `REDIS_CONNECTION_STRING` | `redis://:${REDIS_PASSWORD:?run make env}@redis:6379/0` |
    | `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` | `langfuse` |
    | `LANGFUSE_S3_EVENT_UPLOAD_PREFIX` | `events/` |
    | `LANGFUSE_S3_EVENT_UPLOAD_REGION` | `${S3_REGION:-auto}` |
    | `LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT` | `http://minio:9000` |
    | `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` | `${S3_ACCESS_KEY_ID:-stackr}` |
    | `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY` | `${S3_SECRET_ACCESS_KEY:?run make env}` |
    | `LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE` | `true` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_BUCKET` | `langfuse` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_PREFIX` | `media/` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_REGION` | `${S3_REGION:-auto}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT` | `http://minio:9000` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID` | `${S3_ACCESS_KEY_ID:-stackr}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY` | `${S3_SECRET_ACCESS_KEY:?run make env}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE` | `true` |

### `langfuse-web`

Langfuse's UI and public API. Receives traces from the Collector, and runs the migrations on start.

| Property | Value |
|---|---|
| Profiles | `langfuse` |
| Image | `langfuse/langfuse`, pinned by tag in `compose.yaml` |
| Published ports | 3300 (`LANGFUSE_PORT`) → 3000 |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | none |
| Depends on | `db-init` (completed), `redis` (healthy), `minio` (healthy), `clickhouse` (healthy) |
| Health check | `wget -q -O /dev/null http://127.0.0.1:3000/api/public/health`, every 5s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `DATABASE_URL` | `postgresql://langfuse:${LANGFUSE_DB_PASSWORD:?run make env}@${STACKR_DB_HOST:-supabase_db_stackr-supabase}:5432/langfuse` |
    | `SALT` | `${LANGFUSE_SALT:?run make env}` |
    | `ENCRYPTION_KEY` | `${LANGFUSE_ENCRYPTION_KEY:?run make env}` |
    | `NEXTAUTH_URL` | `http://localhost:${LANGFUSE_PORT:-3300}` |
    | `TELEMETRY_ENABLED` | `false` |
    | `HOSTNAME` | `0.0.0.0` |
    | `CLICKHOUSE_URL` | `http://clickhouse:8123` |
    | `CLICKHOUSE_MIGRATION_URL` | `clickhouse://clickhouse:9000` |
    | `CLICKHOUSE_USER` | `langfuse` |
    | `CLICKHOUSE_PASSWORD` | `${CLICKHOUSE_PASSWORD:?run make env}` |
    | `CLICKHOUSE_CLUSTER_ENABLED` | `false` |
    | `REDIS_CONNECTION_STRING` | `redis://:${REDIS_PASSWORD:?run make env}@redis:6379/0` |
    | `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` | `langfuse` |
    | `LANGFUSE_S3_EVENT_UPLOAD_PREFIX` | `events/` |
    | `LANGFUSE_S3_EVENT_UPLOAD_REGION` | `${S3_REGION:-auto}` |
    | `LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT` | `http://minio:9000` |
    | `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` | `${S3_ACCESS_KEY_ID:-stackr}` |
    | `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY` | `${S3_SECRET_ACCESS_KEY:?run make env}` |
    | `LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE` | `true` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_BUCKET` | `langfuse` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_PREFIX` | `media/` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_REGION` | `${S3_REGION:-auto}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT` | `http://localhost:${MINIO_PORT:-9000}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID` | `${S3_ACCESS_KEY_ID:-stackr}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY` | `${S3_SECRET_ACCESS_KEY:?run make env}` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE` | `true` |
    | `NEXTAUTH_SECRET` | `${LANGFUSE_NEXTAUTH_SECRET:?run make env}` |
    | `AUTH_DISABLE_SIGNUP` | `true` |
    | `LANGFUSE_S3_MEDIA_UPLOAD_INTERNAL_ENDPOINT` | `http://minio:9000` |
    | `LANGFUSE_INIT_ORG_ID` | `${LANGFUSE_INIT_ORG_ID:-stackr}` |
    | `LANGFUSE_INIT_ORG_NAME` | `${LANGFUSE_INIT_ORG_ID:-stackr}` |
    | `LANGFUSE_INIT_PROJECT_ID` | `${LANGFUSE_INIT_PROJECT_ID:-stackr}` |
    | `LANGFUSE_INIT_PROJECT_NAME` | `${LANGFUSE_INIT_PROJECT_ID:-stackr}` |
    | `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` | `${LANGFUSE_PUBLIC_KEY:?run make env}` |
    | `LANGFUSE_INIT_PROJECT_SECRET_KEY` | `${LANGFUSE_SECRET_KEY:?run make env}` |
    | `LANGFUSE_INIT_USER_EMAIL` | `${LANGFUSE_ADMIN_EMAIL:-admin@stackr.local}` |
    | `LANGFUSE_INIT_USER_NAME` | `admin` |
    | `LANGFUSE_INIT_USER_PASSWORD` | `${LANGFUSE_ADMIN_PASSWORD:?run make env}` |

### `litellm`

The LLM gateway port: the LiteLLM proxy's OpenAI-compatible API.

| Property | Value |
|---|---|
| Profiles | `gateway` |
| Image | `ghcr.io/berriai/litellm`, pinned by tag in `compose.yaml` |
| Published ports | 4400 (`LITELLM_PORT`) → 4000 |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | `./deploy/litellm/config.yaml` → `/etc/litellm/config.yaml` (read-only) |
| Depends on | `db-init` (completed), `redis` (healthy) |
| Runs | `--config /etc/litellm/config.yaml --port 4000` |
| Health check | `python -c import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:4000/health/readiness', timeout=3).status != 200)`, every 5s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `LITELLM_MASTER_KEY` | `${LITELLM_MASTER_KEY:?run make env}` |
    | `LITELLM_SALT_KEY` | `${LITELLM_SALT_KEY:?run make env}` |
    | `DATABASE_URL` | `postgresql://litellm:${LITELLM_DB_PASSWORD:?run make env}@${STACKR_DB_HOST:-supabase_db_stackr-supabase}:5432/litellm` |
    | `REDIS_URL` | `redis://:${REDIS_PASSWORD:?run make env}@redis:6379/1` |
    | `ANTHROPIC_API_KEY` | `${ANTHROPIC_API_KEY:-}` |
    | `OPENAI_API_KEY` | `${OPENAI_API_KEY:-}` |
    | `GEMINI_API_KEY` | `${GEMINI_API_KEY:-}` |
    | `OPENROUTER_API_KEY` | `${OPENROUTER_API_KEY:-}` |
    | `LM_STUDIO_API_BASE` | `${LM_STUDIO_API_BASE:-http://host.docker.internal:1234/v1}` |
    | `OMLX_API_BASE` | `${OMLX_API_BASE:-http://host.docker.internal:4243/v1}` |
    | `LITELLM_OTEL_V2` | `${STACKR_GATEWAY_TELEMETRY:-true}` |
    | `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` |
    | `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |
    | `OTEL_SERVICE_NAME` | `litellm` |
    | `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment.name=${STACKR_ENVIRONMENT:-local}` |
    | `LITELLM_OTEL_INTEGRATION_ENABLE_METRICS` | `${STACKR_GATEWAY_TELEMETRY:-true}` |
    | `LITELLM_LOCAL_MODEL_COST_MAP` | `True` |
    | `LITELLM_MODE` | `PRODUCTION` |

### `telemetrygen`

Sends test telemetry for scripts/smoke; not a service that stays up.

| Property | Value |
|---|---|
| Profiles | `smoke` |
| Image | `ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen`, pinned by tag in `compose.yaml` |
| Published ports | none |
| Networks | `stackr` |
| Volumes | none |
| Depends on | none |

<!-- end generated -->

## The file

??? example "The whole file: `compose.yaml`"

    ```yaml
    --8<-- "compose.yaml"
    ```
