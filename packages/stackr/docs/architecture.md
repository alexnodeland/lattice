# Architecture

> **Status:** accepted design, being built in the phases tracked by [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). This document is evergreen: it is updated in the same pull request as the change it describes, and the table below shows what exists today. Decisions are recorded in [`adr/`](adr/README.md), and proposals in [`rfcs/`](rfcs/README.md).

| Part | Status |
|---|---|
| Foundation: layout, `make`, generated secrets, static validation in CI | Implemented |
| `observability` profile: OpenTelemetry Collector, Prometheus, Tempo, Loki, Pyroscope, Grafana | Implemented |
| `langfuse` profile: Langfuse web and worker, ClickHouse, Valkey, MinIO | Implemented |
| Local Supabase, through its CLI: the default database adapter | Implemented |
| `postgres` profile: plain PostgreSQL, the alternative database adapter | Implemented |
| `gateway` profile: the LiteLLM proxy | Planned (phase 4) |
| The application template (Copier) and the `app` profile | Planned (phase 5) |
| Documentation site | Planned (phase 6) |

## What stackr is

stackr is the **infrastructure template** for applications built on [artifactr](https://github.com/alexnodeland/artifactr), [reflexr](https://github.com/alexnodeland/reflexr) and evalr. It has two parts:

- **The stack:** the services those applications run on (a database platform, an LLM gateway, telemetry and LLM observability), as one Docker Compose project with profiles, beside local Supabase.
- **The application template:** a Copier template that scaffolds an application already wired to the stack.

The libraries emit OpenTelemetry through its API only, reach models through the LiteLLM proxy, and ship their own Grafana dashboards. stackr is where those pieces are configured to meet.

## Ports and adapters

Applications talk only to **ports**: a stable protocol at a stable address, configured by a few settings. Behind each port is an **adapter**, the service that implements it, and swapping an adapter changes stackr's configuration, never an application's ([ADR-0005](adr/0005-ports-and-adapters-for-the-stack.md)). Compose profiles are adapter sets.

| Port | Contract | Settings an application reads | Default adapter | Status |
|---|---|---|---|---|
| Telemetry | OTLP to the Collector: gRPC 4317, HTTP 4318 | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | The Collector, exporting to Tempo, Prometheus, Loki and Langfuse | Implemented |
| Profiles | Pyroscope's push API | `PYROSCOPE_SERVER_ADDRESS` | Pyroscope | Implemented |
| LLM gateway | OpenAI-compatible HTTP API, with models named by alias or group | `LITELLM_BASE_URL`, `LITELLM_API_KEY`; `OPENAI_BASE_URL`, `OPENAI_API_KEY` for OpenAI SDKs | The LiteLLM proxy | Planned (phase 4) |
| Database | A PostgreSQL connection string | `DATABASE_URL` | Local Supabase's PostgreSQL; plain PostgreSQL as the alternative | Implemented |
| Object storage | The S3 API | `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_FORCE_PATH_STYLE` | MinIO | Implemented |
| Identity | JWTs, verified against the issuer's key set | `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE` | Supabase Auth | Planned (phase 5) |
| Evaluation data | Langfuse's public API, for scores and datasets | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Self-hosted Langfuse | Implemented |

The settings are a contract with the libraries' extras and the application template, which generates applications wired to these ports only. The stack's own services use the same ports: Langfuse reaches PostgreSQL, S3 and the Redis protocol through settings in `.env`, so their adapters can change as well. Profiles and evaluation data are the two narrow ports: profiles go to Pyroscope directly until OTLP profiles are stable in the Collector, and Langfuse's API carries scores and datasets, never traces.

## Layout

```
compose.yaml        the stack: one Compose project, with profiles
.env.example        settings and placeholders; `make env` turns it into .env
versions.env        versions pinned outside compose.yaml: the Supabase CLI, the libraries' dashboards
deploy/<service>/   each service's configuration, mounted read-only
deploy/postgres/    init.sql: each service's role and database, created by db-init
supabase/           the Supabase CLI project: config.toml (project id stackr-supabase) and seed.sql
scripts/            setup-env, validate, smoke, fetch-dashboards and check-config, run by make and CI
docs/               this document, ADRs and RFCs
```

## Conventions

- **One Compose project, named `stackr`,** with profiles, so only what a task needs runs ([ADR-0001](adr/0001-compose-first-with-profiles.md)).
- **A fixed network name, `stackr`.** The libraries' dev containers and applications join it as an external network and reach every service by name, such as `otel-collector:4317` ([ADR-0006](adr/0006-networks-and-published-ports.md)).
- **Published ports bind to `STACKR_BIND`,** `127.0.0.1` by default, so the stack is reachable from this machine only. Each port is a setting in `.env`. Local Supabase's ports are the exception: its CLI publishes them on every interface ([ADR-0009](adr/0009-local-supabase-as-the-database-adapter.md)).
- **Images run natively.** `make` unexports `DOCKER_DEFAULT_PLATFORM`, which would otherwise run them under emulation.
- **Images are pinned** to versions, and Dependabot proposes updates.
- **Secrets are generated** into a gitignored `.env` by `scripts/setup-env`. `.env.example` holds only settings and placeholders. Compose fails when a required value is missing, rather than starting a service with an empty secret.

## The observability profile

| Service | Image | Role | Published port |
|---|---|---|---|
| `otel-collector` | `otel/opentelemetry-collector-contrib` | The telemetry port: receives OTLP, exports each signal to its backend | 4317 (gRPC), 4318 (HTTP) |
| `tempo` | `grafana/tempo` | Traces, with its metrics generator for span metrics and service graphs | 3200 |
| `prometheus` | `prom/prometheus` | Metrics: OTLP from the Collector, remote write from Tempo, and scrapes of the stack's own services | 9090 |
| `loki` | `grafana/loki` | Logs, over OTLP | 3100 |
| `pyroscope` | `grafana/pyroscope` | Profiles, pushed by applications | 4040 |
| `grafana` | `grafana/grafana` | Dashboards and exploration; signs in as `admin` with `GRAFANA_ADMIN_PASSWORD` from `.env` | 3000 |

The image versions are pinned in `compose.yaml`.

### The telemetry path

```mermaid
graph LR
    app["application<br/>(artifactr, reflexr, evalr)"] -- "OTLP" --> collector["otel-collector"]
    collector -- "OTLP gRPC" --> tempo["tempo"]
    collector -- "OTLP HTTP /api/v1/otlp" --> prometheus["prometheus"]
    collector -- "OTLP HTTP /otlp" --> loki["loki"]
    collector -- "OTLP HTTP /api/public/otel<br/>+ x-langfuse-ingestion-version: 4" --> langfuse["langfuse-web"]
    tempo -- "span metrics, service graphs<br/>(remote write)" --> prometheus
    app -- "profiles" --> pyroscope["pyroscope"]
    grafana["grafana"] --> tempo & prometheus & loki & pyroscope
```

How each signal is routed, and why metrics use Prometheus's OTLP receiver, is in [ADR-0007](adr/0007-how-telemetry-reaches-the-backends.md). The Collector's configuration is `deploy/otel-collector/config.yaml`; replacing a backend means replacing its exporter there. Traces go to Langfuse only when the `langfuse` profile runs: the traces pipeline takes its exporters from `STACKR_TRACES_EXPORTERS`, which `make up` sets from the chosen profiles.

### Metric names in Prometheus

Prometheus translates OTLP metrics with its default strategy. The libraries' dashboards query the translated names:

| OTLP metric (unit) | Kind | In Prometheus |
|---|---|---|
| `artifactr.commands` (`1`) | Counter | `artifactr_commands_total` |
| `artifactr.commit.duration` (`s`) | Histogram | `artifactr_commit_duration_seconds_bucket`, `_sum`, `_count` |
| `artifactr.stream.connections` (`{connection}`) | Up-down counter | `artifactr_stream_connections` |

- `service.name` becomes the `job` label. `deployment.environment.name` and `service.version` are copied from the resource onto every series (as `deployment_environment_name` and `service_version`); other resource attributes are on `target_info`.
- Data point attributes become labels with dots turned into underscores: `artifactr.command.type` becomes `artifactr_command_type`.
- Tempo's metrics generator adds `traces_spanmetrics_calls_total`, `traces_spanmetrics_latency_bucket` and `traces_service_graph_request_total`, labelled by `service`, `span_name`, `span_kind` and `status_code`.

### Grafana

- **Data sources** are provisioned with fixed uids, which dashboards refer to: `prometheus`, `tempo`, `loki` and `pyroscope`.
- **Links between signals:** a span links to its service's logs around the span's time, filtered to the trace (Loki); to its service's span metrics (Prometheus); and to its service's CPU profile (Pyroscope). Log lines with a `trace_id` link to the trace, and histogram exemplars link to the trace that produced them. Tempo's service map and node graph read the service graph metrics.
- **Dashboards** are files under `deploy/grafana/dashboards/`, one folder per directory:
  - `stackr/` is committed. **Collector health** (`stackr-collector`) shows what the Collector receives, what each backend receives, send failures, queues, memory and CPU, and whether each of the stack's services is up.
  - `artifactr/` and `reflexr/` are the libraries' own dashboards, downloaded by `make dashboards` (and `make up`) at the release pinned in `versions.env`, and gitignored.

### The libraries' dashboards

Each library publishes its dashboards with every release, as one archive of dashboard JSON files at

```
https://github.com/alexnodeland/<library>/releases/download/v<version>/<library>-dashboards-<version>.tar.gz
```

`versions.env` pins the release for each library (`ARTIFACTR_DASHBOARDS_VERSION`, `REFLEXR_DASHBOARDS_VERSION`), with an optional sha256 of the archive. `scripts/fetch-dashboards` downloads each pinned archive, checks its sha256, and replaces the library's folder. A library with no version pinned is skipped, and a failed download is a warning (an error with `--strict`), so `make up` works offline and before a library has published. To move to a new release, change its version and sha256 in `versions.env`, then run `make dashboards` and `make smoke`.

## The langfuse profile

Self-hosted Langfuse 4, for LLM traces, sessions, scores and datasets ([ADR-0008](adr/0008-langfuse-and-its-services.md)).

| Service | Image | Role | Published port |
|---|---|---|---|
| `langfuse-web` | `langfuse/langfuse` | The UI and the public API; receives traces from the Collector; runs the PostgreSQL and ClickHouse migrations on start | 3300 |
| `langfuse-worker` | `langfuse/langfuse-worker` | Processes ingestion and evaluation jobs from the queues | none |
| `clickhouse` | `clickhouse/clickhouse-server` | Traces, observations and scores | none |
| `redis` | `valkey/valkey` | The Redis protocol: Langfuse's queues and cache (database 0), shared with the gateway (database 1), with `noeviction` | none |
| `minio` | `cgr.dev/chainguard/minio`, by digest | The S3 port: Langfuse's event and media bucket, `langfuse` | 9000 (S3), 9001 (console) |
| `db-init` | `postgres` | Creates each service's role and database on the database adapter, then exits | none |

- **First start** creates an organisation and project (`stackr`), the project's API keys (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`) and an admin user (`LANGFUSE_ADMIN_EMAIL`, `LANGFUSE_ADMIN_PASSWORD`), all from `.env`. Sign-up is disabled. The UI is at <http://localhost:3300>.
- **Traces arrive through the Collector,** never directly: its `otlp_http/langfuse` exporter sends them to `/api/public/otel` with Basic credentials derived from the project's keys (`LANGFUSE_OTLP_AUTH`) and the `x-langfuse-ingestion-version: 4` header. Applications use Langfuse's API only for scores and datasets, the evaluation data port.
- **Langfuse 4 reads trace-level attributes from every span:** `session.id`, `user.id`, `langfuse.trace.name` and tags must be on each span the libraries own, not only the root.

## The database

The stack's services keep their data in PostgreSQL through the database port. One setting in `.env`, `STACKR_DATABASE`, chooses the adapter, and `make` derives the rest ([ADR-0009](adr/0009-local-supabase-as-the-database-adapter.md)):

| `STACKR_DATABASE` | Adapter | Started by | Host on the network | Admin | Published port |
|---|---|---|---|---|---|
| `supabase` (default) | Local Supabase's PostgreSQL | `make up`, through the Supabase CLI | `supabase_db_stackr-supabase` | `postgres`, with Supabase's fixed local password `postgres` | 54322 |
| `postgres` | Plain PostgreSQL, the `postgres` profile | `make up`, through Compose | `postgres` | `postgres`, with `POSTGRES_ADMIN_PASSWORD` from `.env` | 55432 |

- **Supabase starts with the profiles that need it:** `make up` runs `supabase start` when a profile that keeps data in PostgreSQL (`langfuse`, and the gateway in phase 4) is chosen. `make up PROFILES=observability` leaves it off.
- **`db-init`** runs `deploy/postgres/init.sql` with `psql` on every start, before the services that need it. For each service (Langfuse now; the gateway in phase 4) it creates a login role with the password from `.env`, resets the password so the two stay in step, and creates the service's database, owned by its role and in UTC. On Supabase, whose `postgres` role is not a superuser, it first grants itself the role, which PostgreSQL 16 and later require for creating a database owned by it.
- **After `supabase db reset` or `supabase stop --no-backup`,** which delete Supabase's database volume, the next `make up` recreates the stack's databases, empty.

## Local Supabase

The `supabase/` directory is a Supabase CLI project, close to what `supabase init` generates. Its project id is `stackr-supabase`: it names the containers and the network, and differs from the Compose project's name because the CLI labels its containers as a Compose project too. The CLI version is pinned in `versions.env`; `make` uses an installed `supabase`, or runs the pinned version through `npx`.

| Service | Address on the host | On the network |
|---|---|---|
| API gateway (REST, Auth, Storage, Realtime, GraphQL) | <http://localhost:54321> | `supabase_kong_stackr-supabase:8000` |
| PostgreSQL | `postgresql://postgres:postgres@localhost:54322/postgres` | `supabase_db_stackr-supabase:5432` |
| Studio | <http://localhost:54323> | |
| Mailpit (the emails Auth would send) | <http://localhost:54324> | |
| Analytics | <http://localhost:54327> | |

- **Networking:** Supabase's containers are on `supabase_network_stackr-supabase`. `make up` creates that network before `supabase start`, so the CLI joins it rather than owning it, and `supabase stop` leaves it in place. The services that use PostgreSQL join it as well as `stackr`. A dev container that needs Supabase's PostgreSQL by name joins it too, or uses port 54322 on the host.
- **Keys and URLs:** `supabase status` prints the API URL, the local publishable and secret keys, and the rest. They are Supabase's well-known local development values.
- **Skipping services:** `make up SUPABASE_START_FLAGS="-x studio,imgproxy"` passes flags to `supabase start`; CI uses this to start only what the smoke test needs.

## Commands

| Command | What it does |
|---|---|
| `make env` | Create or update `.env`, generating local secrets; re-running keeps existing values |
| `make up` | Start the stack, or the profiles named in `PROFILES` (`make up PROFILES=observability`), with local Supabase or the `postgres` profile when they need a database |
| `make down` / `make reset` | Stop the stack and local Supabase, keeping or deleting their data volumes |
| `make dashboards` | Download the libraries' dashboards at the releases pinned in `versions.env` |
| `make validate` | Check every configuration without starting containers |
| `make smoke` | Send test telemetry through the running stack and check it arrives |

## Validation

CI checks the stack two ways on every pull request, with the same scripts as `make validate` and `make smoke`.

**Statically,** without starting the stack:

- every YAML file with yamllint
- the Compose configuration for each profile on its own and for all of them together, failing on warnings
- each service's configuration with that service's own validator, run from the image `compose.yaml` pins: `otelcol-contrib validate` for the Collector, `promtool check config` for Prometheus, `-config.verify` for Tempo and `-verify-config` for Loki
- the Grafana dashboards: valid JSON, unique uids, and only the provisioned data sources
- the Supabase project: its id differs from the Compose project's, and `compose.yaml` and the Makefile use the names it gives
- the scripts, with shellcheck and ruff

**With containers,** the smoke job starts each profile and runs `scripts/smoke`: `observability` alone, and `observability langfuse` on each database adapter. For `observability`, it sends a trace, a metric and a log through the Collector with `telemetrygen`, and finds:

- the trace in Tempo, by a TraceQL search on the run's id
- the metric in Prometheus as `stackr_smoke_total`, which also checks the name translation above
- the log in Loki
- Tempo's span metrics, and the Collector's own metrics, in Prometheus
- Grafana's four data sources healthy, and the Collector dashboard provisioned

For the database adapter, it queries over `db-init`'s own connection that Langfuse's database exists, and with local Supabase that its API answers. For `langfuse` (with `observability`), it sends a trace with a known id to the Collector's HTTP port and finds it in Langfuse through the public API (`/api/public/v2/observations`) and in Tempo, which checks the Collector's route and credentials and Langfuse's ingestion end to end.
