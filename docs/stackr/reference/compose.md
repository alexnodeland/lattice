# Compose services and profiles

`compose.yaml` is one Compose project, `stackr`, whose services are grouped in profiles ([The stack and its profiles](../guides/stack.md)). Local Supabase isn't in it: its CLI runs it beside the project ([Local Supabase](../guides/supabase.md)).

## Profiles

<!-- generated: compose-profiles -->

| Profile | Services | In `make up`'s default |
|---|---|---|
| `observability` | `otel-collector`, `tempo`, `prometheus`, `prom-label-proxy`, `loki`, `pyroscope`, `grafana` | yes |
| `postgres` | `postgres` | no |
| `langfuse` | `db-init`, `redis`, `minio`, `clickhouse`, `langfuse-worker`, `langfuse-web` | yes |
| `gateway` | `db-init`, `redis`, `litellm` | yes |
| `auth` | `db-init`, `gotrue` | no |
| `clickhouse` | `clickhouse` | no |
| `analytics` | `clickhouse` | no |
| `analytics-init` | `clickhouse`, `clickhouse-init` | no |
| `umami` | `umami`, `umami-db-init`, `umami-retention` | no |
| `umami-init` | `umami`, `umami-db-init`, `umami-init` | no |
| `smoke` | `telemetrygen`, `probe` | no |

<!-- end generated -->

`make up PROFILES="..."` chooses others. `postgres` is added by `make up` when `STACKR_DATABASE=postgres` and a profile needs a database; `smoke` holds `telemetrygen`, which `scripts/smoke` runs once per signal.

## Networks

<!-- generated: compose-networks -->

| Network | Created | Joined by |
|---|---|---|
| `stackr` | by Compose | `otel-collector`, `tempo`, `prometheus`, `prom-label-proxy`, `loki`, `pyroscope`, `grafana`, `postgres`, `db-init`, `gotrue`, `redis`, `minio`, `clickhouse`, `clickhouse-init`, `umami-db-init`, `langfuse-worker`, `langfuse-web`, `litellm`, `telemetrygen`, `probe` |
| `supabase_network_stackr-supabase` | by `make up`, if missing | `db-init`, `langfuse-worker`, `langfuse-web`, `litellm`, `probe` |
| `stackr-umami` | by `make up`, if missing | `umami`, `umami-init` |
| `umami-db` | by Compose | `postgres`, `umami`, `umami-retention` |
| `umami-ui` | by Compose | `umami` |

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
| Image | `otel/opentelemetry-collector-contrib`, pinned by tag and digest in `compose.yaml` |
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
| Image | `grafana/tempo`, pinned by tag and digest in `compose.yaml` |
| Published ports | 3200 (`TEMPO_PORT`) → 3200 |
| Networks | `stackr` |
| Volumes | `./deploy/tempo/tempo.yaml` → `/etc/tempo/tempo.yaml` (read-only), `tempo-data` → `/var/tempo` |
| Depends on | `prometheus` |
| Runs | `-config.file=/etc/tempo/tempo.yaml -config.expand-env=true` |
| Restart | `unless-stopped` |

### `prometheus`

Metrics: OTLP from the Collector, remote write from Tempo, and scrapes of the stack's own services.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `prom/prometheus`, pinned by tag and digest in `compose.yaml` |
| Published ports | 9090 (`PROMETHEUS_PORT`) → 9090 |
| Networks | `stackr` |
| Volumes | `./deploy/prometheus/prometheus.yml` → `/etc/prometheus/prometheus.yml` (read-only), `prometheus-data` → `/prometheus` |
| Depends on | none |
| Runs | `--config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --storage.tsdb.retention.time=15d --web.enable-otlp-receiver --web.enable-remote-write-receiver --enable-feature=exemplar-storage` |
| Health check | `wget -q -O /dev/null http://127.0.0.1:9090/-/ready`, every 5s |
| Restart | `unless-stopped` |

### `prom-label-proxy`

portalr's path to Prometheus: it rewrites every query's selectors to the tenant its `tenant_id` parameter names. Grafana keeps its direct data source.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `quay.io/prometheuscommunity/prom-label-proxy`, pinned by tag and digest in `compose.yaml` |
| Published ports | 9091 (`PROM_LABEL_PROXY_PORT`) → 8080 |
| Networks | `stackr` |
| Volumes | none |
| Depends on | `prometheus` |
| Runs | `-label=tenant_id -upstream=http://prometheus:9090 -insecure-listen-address=0.0.0.0:8080 -internal-listen-address=127.0.0.1:8081` |
| Health check | `wget -q -O /dev/null http://127.0.0.1:8081/metrics`, every 5s |
| Restart | `unless-stopped` |

### `loki`

Logs, over OTLP.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `grafana/loki`, pinned by tag and digest in `compose.yaml` |
| Published ports | 3100 (`LOKI_PORT`) → 3100 |
| Networks | `stackr` |
| Volumes | `./deploy/loki/loki.yaml` → `/etc/loki/loki.yaml` (read-only), `loki-data` → `/loki` |
| Depends on | none |
| Runs | `-config.file=/etc/loki/loki.yaml -config.expand-env=true` |
| Restart | `unless-stopped` |

### `pyroscope`

Profiles, pushed by applications.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `grafana/pyroscope`, pinned by tag and digest in `compose.yaml` |
| Published ports | 4040 (`PYROSCOPE_PORT`) → 4040 |
| Networks | `stackr` |
| Volumes | `./deploy/pyroscope/config.yaml` → `/etc/pyroscope/config.yaml` (read-only), `pyroscope-data` → `/data` |
| Depends on | none |
| Runs | `-config.file=/etc/pyroscope/config.yaml -config.expand-env=true` |
| Restart | `unless-stopped` |

### `grafana`

Dashboards and exploration, over the four backends.

| Property | Value |
|---|---|
| Profiles | `observability` |
| Image | `stackr-grafana`, built from `packages/stackr/deploy/grafana/Dockerfile`, which pins its base |
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
    | `PROMETHEUS_ADDRESS` | `prometheus` |
    | `TEMPO_ADDRESS` | `tempo` |
    | `LOKI_ADDRESS` | `loki` |
    | `PYROSCOPE_ADDRESS` | `pyroscope` |
    | `CLICKHOUSE_ADDRESS` | `clickhouse` |
    | `CLICKHOUSE_GRAFANA_PASSWORD` | `${CLICKHOUSE_GRAFANA_PASSWORD:?run make env}` |

### `postgres`

Plain PostgreSQL, the alternative database adapter, used when STACKR_DATABASE is `postgres`.

| Property | Value |
|---|---|
| Profiles | `postgres` |
| Image | `postgres`, pinned by tag and digest in `compose.yaml` |
| Published ports | 55432 (`POSTGRES_PORT`) → 5432 |
| Networks | `stackr`, `umami-db` |
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
| Profiles | `langfuse`, `gateway`, `auth` |
| Image | `postgres`, pinned by tag and digest in `compose.yaml` |
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
    | `AUTH_DB_PASSWORD` | `${AUTH_DB_PASSWORD:?run make env}` |

### `gotrue`

GoTrue, Supabase's auth server alone: the identity port on the `postgres` adapter, signing tokens with an ES256 key set (RFC-0004).

| Property | Value |
|---|---|
| Profiles | `auth` |
| Image | `supabase/gotrue`, pinned by tag and digest in `compose.yaml` |
| Published ports | 9999 (`AUTH_PORT`) → 9999 |
| Networks | `stackr` |
| Volumes | none |
| Depends on | `db-init` (completed) |
| Health check | `wget -q -O /dev/null http://127.0.0.1:9999/health`, every 3s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `GOTRUE_API_HOST` | `0.0.0.0` |
    | `PORT` | `9999` |
    | `API_EXTERNAL_URL` | `${AUTH_PUBLIC_URL:-http://localhost:9999}` |
    | `GOTRUE_SITE_URL` | `${AUTH_SITE_URL:-http://localhost:8800}` |
    | `GOTRUE_DB_DRIVER` | `postgres` |
    | `GOTRUE_DB_DATABASE_URL` | `postgres://gotrue:${AUTH_DB_PASSWORD:?run make env}@${STACKR_DB_HOST:-postgres}:5432/auth` |
    | `GOTRUE_JWT_ISSUER` | `${AUTH_PUBLIC_URL:-http://localhost:9999}` |
    | `GOTRUE_JWT_KEYS` | `${AUTH_JWT_KEYS:?run make env}` |
    | `GOTRUE_JWT_SECRET` | `${AUTH_JWT_SECRET:?run make env}` |
    | `GOTRUE_JWT_AUD` | `authenticated` |
    | `GOTRUE_JWT_DEFAULT_GROUP_NAME` | `authenticated` |
    | `GOTRUE_JWT_ADMIN_ROLES` | `service_role` |
    | `GOTRUE_JWT_EXP` | `3600` |
    | `GOTRUE_EXTERNAL_EMAIL_ENABLED` | `true` |
    | `GOTRUE_DISABLE_SIGNUP` | `${AUTH_DISABLE_SIGNUP:-true}` |
    | `GOTRUE_SMTP_HOST` | `${AUTH_SMTP_HOST:-}` |
    | `GOTRUE_SMTP_PORT` | `${AUTH_SMTP_PORT:-587}` |
    | `GOTRUE_SMTP_USER` | `${AUTH_SMTP_USER:-}` |
    | `GOTRUE_SMTP_PASS` | `${AUTH_SMTP_PASSWORD:-}` |
    | `GOTRUE_SMTP_ADMIN_EMAIL` | `${AUTH_SMTP_SENDER:-}` |

### `redis`

Valkey, for the Redis protocol: Langfuse's queues and cache in database 0, the gateway's routing state and cache in database 1.

| Property | Value |
|---|---|
| Profiles | `langfuse`, `gateway` |
| Image | `valkey/valkey`, pinned by tag and digest in `compose.yaml` |
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

Langfuse's traces, observations and scores, and portalr's analytics events.

| Property | Value |
|---|---|
| Profiles | `clickhouse`, `langfuse`, `analytics`, `analytics-init` |
| Image | `clickhouse/clickhouse-server`, pinned by tag and digest in `compose.yaml` |
| Published ports | 8123 (`CLICKHOUSE_HTTP_PORT`) on 127.0.0.1 only → 8123 |
| Networks | `stackr` |
| Volumes | `./deploy/clickhouse/users.xml` → `/etc/clickhouse-server/users.d/users.xml` (read-only), `./deploy/clickhouse/analytics-users.xml` → `/etc/clickhouse-server/users.d/analytics-users.xml` (read-only), `./deploy/clickhouse/analytics.xml` → `/etc/clickhouse-server/config.d/analytics.xml` (read-only), `clickhouse-data` → `/var/lib/clickhouse`, `clickhouse-logs` → `/var/log/clickhouse-server` |
| Depends on | none |
| Health check | `wget --no-verbose --tries=1 --spider http://127.0.0.1:8123/ping`, every 3s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `CLICKHOUSE_SKIP_USER_SETUP` | `1` |
    | `CLICKHOUSE_ADMIN_PASSWORD` | `${CLICKHOUSE_ADMIN_PASSWORD:?run make env}` |
    | `CLICKHOUSE_LANGFUSE_PASSWORD` | `${CLICKHOUSE_PASSWORD:?run make env}` |
    | `CLICKHOUSE_ANALYTICS_WRITER_PASSWORD` | `${CLICKHOUSE_ANALYTICS_WRITER_PASSWORD:?run make env}` |
    | `CLICKHOUSE_ANALYTICS_PASSWORD` | `${CLICKHOUSE_ANALYTICS_PASSWORD:?run make env}` |
    | `CLICKHOUSE_GRAFANA_PASSWORD` | `${CLICKHOUSE_GRAFANA_PASSWORD:?run make env}` |

### `clickhouse-init`

Makes portalr's analytics database and its events table, with the deployment's retention, each time `make up` starts the analytics profile, then exits.

| Property | Value |
|---|---|
| Profiles | `analytics-init` |
| Image | `clickhouse/clickhouse-server`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `stackr` |
| Volumes | `./deploy/clickhouse/analytics.sql` → `/analytics.sql` (read-only) |
| Depends on | `clickhouse` (healthy) |
| Runs | `sh -c` |
| Restart | `no` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `CLICKHOUSE_PASSWORD` | `${CLICKHOUSE_ADMIN_PASSWORD:?run make env}` |
    | `ANALYTICS_RETENTION_DAYS` | `${ANALYTICS_RETENTION_DAYS:-395}` |

### `umami`

Umami, operators' journeys: portalr's relay sends it a copy of consented events, on a network only the application joins. On the postgres adapter alone. Its port, on 127.0.0.1 alone, is its UI's and its ingest's too: anything on this machine may post events to it (ADR-0050).

| Property | Value |
|---|---|
| Profiles | `umami`, `umami-init` |
| Image | `ghcr.io/umami-software/umami`, pinned by tag and digest in `compose.yaml` |
| Published ports | 3400 (`UMAMI_PORT`) on 127.0.0.1 only → 3000 |
| Networks | `stackr-umami`, `umami-db`, `umami-ui` |
| Volumes | none |
| Depends on | `umami-db-init` (completed) |
| Health check | `wget -q -O /dev/null http://127.0.0.1:3000/api/heartbeat`, every 5s |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `DATABASE_URL` | `postgresql://umami:${UMAMI_DB_PASSWORD:?run make env}@postgres:5432/umami?schema=umami` |
    | `APP_SECRET` | `${UMAMI_APP_SECRET:?run make env}` |
    | `DISABLE_TELEMETRY` | `1` |
    | `DISABLE_UPDATES` | `1` |
    | `DISABLE_BOT_CHECK` | `1` |

### `umami-db-init`

Makes Umami's role and database on plain PostgreSQL, with the umami profile alone, then exits.

| Property | Value |
|---|---|
| Profiles | `umami`, `umami-init` |
| Image | `postgres`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `stackr` |
| Volumes | `./deploy/postgres/umami.sql` → `/umami.sql` (read-only) |
| Depends on | `postgres` (healthy, when it runs) |
| Runs | `psql --no-psqlrc --quiet --file=/umami.sql` |
| Restart | `no` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `PGHOST` | `postgres` |
    | `PGPORT` | `5432` |
    | `PGDATABASE` | `postgres` |
    | `PGUSER` | `postgres` |
    | `PGPASSWORD` | `${POSTGRES_ADMIN_PASSWORD:?run make env}` |
    | `PGCONNECT_TIMEOUT` | `10` |
    | `UMAMI_DB_PASSWORD` | `${UMAMI_DB_PASSWORD:?run make env}` |

### `umami-init`

Sets Umami's admin password, and makes portalr's user and website, each time `make up` starts the umami profile, then exits.

| Property | Value |
|---|---|
| Profiles | `umami-init` |
| Image | `curlimages/curl`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `stackr-umami` |
| Volumes | `./deploy/umami/init` → `/init` (read-only) |
| Depends on | `umami` (healthy) |
| Runs | `sh /init` |
| Restart | `no` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `UMAMI_ADMIN_PASSWORD` | `${UMAMI_ADMIN_PASSWORD:?run make env}` |
    | `UMAMI_PORTALR_PASSWORD` | `${UMAMI_PORTALR_PASSWORD:?run make env}` |
    | `UMAMI_WEBSITE_ID` | `${UMAMI_WEBSITE_ID:?run make env}` |
    | `UMAMI_REPLAY` | `${UMAMI_REPLAY:-false}` |

### `umami-retention`

Deletes Umami's session replays older than UMAMI_REPLAY_RETENTION_DAYS (30 by default; 0 keeps them), every six hours, as Umami's own database role. Sessions and journeys stay. It runs whether or not replay is on, so recordings made before it was turned off still expire (portalr ADR-0077).

| Property | Value |
|---|---|
| Profiles | `umami` |
| Image | `postgres`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `umami-db` |
| Volumes | `./deploy/umami/retention` → `/retention` (read-only) |
| Depends on | `umami` (healthy) |
| Runs | `sh /retention` |
| Health check | `test -n "$(find /tmp/umami-retention-ok -mmin -1440)"`, every 5m |
| Restart | `unless-stopped` |

??? note "Environment"

    | Variable | Value |
    |---|---|
    | `PGHOST` | `postgres` |
    | `PGDATABASE` | `umami` |
    | `PGUSER` | `umami` |
    | `PGPASSWORD` | `${UMAMI_DB_PASSWORD:?run make env}` |
    | `PGCONNECT_TIMEOUT` | `10` |
    | `PGOPTIONS` | `-c lock_timeout=10s -c statement_timeout=5min` |
    | `UMAMI_REPLAY_RETENTION_DAYS` | `${UMAMI_REPLAY_RETENTION_DAYS:-30}` |

### `langfuse-worker`

Langfuse's worker: runs ingestion and evaluation jobs from the queues.

| Property | Value |
|---|---|
| Profiles | `langfuse` |
| Image | `langfuse/langfuse-worker`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | none |
| Depends on | `db-init` (completed), `redis` (healthy), `minio` (healthy), `clickhouse` (healthy), `langfuse-web` (healthy) |
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
| Image | `langfuse/langfuse`, pinned by tag and digest in `compose.yaml` |
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
| Image | `ghcr.io/berriai/litellm-non_root`, pinned by tag and digest in `compose.yaml` |
| Published ports | 4400 (`LITELLM_PORT`) → 4000 |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | `./deploy/litellm/config.yaml` → `/etc/litellm/config.yaml` (read-only), `./deploy/litellm/groups/${STACKR_GATEWAY_MODELS:-providers}.yaml` → `/etc/litellm/groups.yaml` (read-only), `${STACKR_UPSTREAM_CA:-/dev/null}` → `/etc/litellm/upstream-ca.pem` (read-only) |
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
    | `STACKR_UPSTREAM_URL` | `${STACKR_UPSTREAM_URL:-}` |
    | `STACKR_UPSTREAM_API_KEY` | `${STACKR_UPSTREAM_API_KEY:-}` |
    | `STACKR_UPSTREAM_DEFAULT_MODEL` | `${STACKR_UPSTREAM_DEFAULT_MODEL:-}` |
    | `STACKR_UPSTREAM_FAST_MODEL` | `${STACKR_UPSTREAM_FAST_MODEL:-}` |
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
| Image | `ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `stackr` |
| Volumes | none |
| Depends on | none |

### `probe`

curl, for scripts/smoke's requests from inside the stack's networks; not a service that stays up.

| Property | Value |
|---|---|
| Profiles | `smoke` |
| Image | `curlimages/curl`, pinned by tag and digest in `compose.yaml` |
| Published ports | none |
| Networks | `stackr`, `supabase_network_stackr-supabase` |
| Volumes | none |
| Depends on | none |

<!-- end generated -->

## The file

??? example "The whole file: `compose.yaml`"

    ```yaml
    --8<-- "packages/stackr/compose.yaml"
    ```
