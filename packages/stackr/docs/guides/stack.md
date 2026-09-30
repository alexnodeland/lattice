# The stack and its profiles

The stack is one Docker Compose project, named `stackr`, whose services are grouped in profiles, beside local Supabase, which its own CLI runs. Only what a task needs runs ([ADR-0001](../adr/0001-compose-first-with-profiles.md)). `make` drives both halves, so the everyday commands are the same whichever profiles and database you choose.

## The profiles

Each profile is an **adapter set**: the services behind one or more of the ports applications talk to ([ADR-0005](../adr/0005-ports-and-adapters-for-the-stack.md)).

| Profile | Runs | The port it serves |
|---|---|---|
| `observability` | The OpenTelemetry Collector, Tempo, Prometheus, Loki, Pyroscope and Grafana | Telemetry (OTLP) and profiles |
| `langfuse` | Langfuse's web server and worker, ClickHouse, MinIO, Valkey and `db-init` | Evaluation data, and object storage (S3) |
| `gateway` | The LiteLLM proxy, Valkey and `db-init` | The LLM gateway |
| `postgres` | Plain PostgreSQL | The database, when `STACKR_DATABASE=postgres` |
| `smoke` | `telemetrygen`, which the smoke test runs once per signal | None: a tool |

`make up` starts `observability`, `langfuse` and `gateway` unless you choose:

```bash
make up                                   # observability, langfuse and gateway
make up PROFILES=observability            # telemetry only: no database, so no Supabase
make up PROFILES="observability gateway"  # telemetry and the gateway, with local Supabase
```

- **Langfuse receives traces only through the Collector,** so `langfuse` without `observability` starts Langfuse with nothing sending to it. Choose both.
- **The gateway sends telemetry only when the Collector runs.** `make up` turns the gateway's OpenTelemetry integration off without `observability`, and leaves Langfuse out of the Collector's trace exporters without `langfuse`, so neither logs export errors to a service that isn't there.
- **`db-init` and Valkey belong to both `langfuse` and `gateway`,** and run once when both are chosen.

The application template adds a sixth profile, `app`, in the generated application's own `compose.yaml` rather than stackr's ([ADR-0011](../adr/0011-the-application-template-in-detail.md)). [The application template](template.md) covers it.

[Compose services and profiles](../reference/compose.md) lists every service with its image, ports, volumes, networks and health check, generated from `compose.yaml`.

## The database adapter

Langfuse and the gateway keep their data in PostgreSQL, through the database port. One setting in `.env` chooses the adapter, and `make` derives everything else from it ([ADR-0009](../adr/0009-local-supabase-as-the-database-adapter.md)):

| `STACKR_DATABASE` | Adapter | Started by | Host on the network | Admin password | Published port |
|---|---|---|---|---|---|
| `supabase` (the default) | Local Supabase's PostgreSQL | `make up`, through the Supabase CLI | `supabase_db_stackr-supabase` | `postgres`, Supabase's fixed local password | 54322 |
| `postgres` | Plain PostgreSQL, the `postgres` profile | `make up`, through Compose | `postgres` | `POSTGRES_ADMIN_PASSWORD` from `.env` | 55432 |

Either way, `db-init` runs `deploy/postgres/init.sql` on every start, before the services that need it. For Langfuse and the gateway it creates a login role with the password from `.env` (resetting it, so the two stay in step) and a database owned by that role, in UTC. It is idempotent, so a `make up` after `supabase db reset` recreates the databases, empty.

A database only starts with a profile that keeps data in it: `make up PROFILES=observability` starts neither Supabase nor the `postgres` profile. [Local Supabase](supabase.md) covers the default adapter in depth.

## What `make up` runs

`make up` is a thin wrapper, so you can see exactly what it does:

1. `make .env`, which runs `make env` only if `.env` is missing or older than `.env.example`
2. `make dashboards`, which downloads the libraries' Grafana dashboards pinned in `versions.env`
3. `docker network create supabase_network_stackr-supabase`, if that network doesn't exist
4. `supabase start`, if a chosen profile needs PostgreSQL and the adapter is Supabase; `SUPABASE_START_FLAGS` passes flags to it, such as `-x studio,imgproxy` to skip services
5. `docker compose --profile ... up --detach --wait`, with three variables derived from the profiles: `STACKR_TRACES_EXPORTERS` (the Collector's trace exporters), `STACKR_GATEWAY_TELEMETRY` (the gateway's telemetry), and, for the `postgres` adapter, `STACKR_DB_HOST` and `STACKR_DB_ADMIN_PASSWORD`

Compose's own defaults for those variables are the full stack on local Supabase, so plain `docker compose --profile observability --profile langfuse --profile gateway up` works too, once local Supabase is running and its network exists. (`--profile '*'` would start the `postgres` and `smoke` profiles as well.) With the `postgres` adapter, set the two database variables yourself, or use `make`.

`make` also unexports `DOCKER_DEFAULT_PLATFORM`. The stack's images are multi-architecture; a platform forced for other work would run them under emulation, where Supabase's Realtime fails to start.

## Networks

- **`stackr`** is the Compose project's network, with a fixed name. Every service is on it, and reaches the others by service name: `otel-collector:4317`, `litellm:4000`, `langfuse-web:3000`. The libraries' dev containers and applications join it as an external network to do the same ([ADR-0006](../adr/0006-networks-and-published-ports.md)).
- **`supabase_network_stackr-supabase`** is local Supabase's network. The services that use PostgreSQL (`db-init`, Langfuse's web server and worker, and the gateway) join it as well, to reach `supabase_db_stackr-supabase` by name. `make up` creates it before `supabase start`, so the CLI joins it rather than owning it, and `supabase stop` never removes it from under running services.

A container that needs both the stack and Supabase's PostgreSQL by name joins both networks, as the application template's app profile and dev container do. From the host, use the published ports instead.

## Published ports

Every port the stack publishes binds to `STACKR_BIND`, `127.0.0.1` by default, so nothing is reachable from other machines unless you choose it. Each port is a setting in `.env`, so one that collides with something else on your machine is one line to change:

| Setting | Default | Service |
|---|---|---|
| `OTLP_GRPC_PORT`, `OTLP_HTTP_PORT` | 4317, 4318 | The Collector's OTLP receivers |
| `PYROSCOPE_PORT` | 4040 | Pyroscope |
| `GRAFANA_PORT` | 3000 | Grafana |
| `PROMETHEUS_PORT` | 9090 | Prometheus |
| `TEMPO_PORT` | 3200 | Tempo's API |
| `LOKI_PORT` | 3100 | Loki's API |
| `LANGFUSE_PORT` | 3300 | Langfuse |
| `MINIO_PORT`, `MINIO_CONSOLE_PORT` | 9000, 9001 | MinIO's S3 API and console |
| `LITELLM_PORT` | 4400 | The gateway |
| `POSTGRES_PORT` | 55432 | Plain PostgreSQL, with the `postgres` adapter |

ClickHouse, Valkey and the Collector's own metrics aren't published: nothing outside the stack uses them. Local Supabase's ports (54321 to 54324 and 54327) are the CLI's to publish, on every interface; see [Security](security.md).

## Everyday commands

| Command | What it does |
|---|---|
| `make up` | Start the chosen profiles, with the database they need |
| `make ps` | Show the Compose services, their state and ports. Local Supabase's containers aren't in the Compose project: `supabase status` shows them |
| `make logs` | Follow the running services' logs |
| `make down` | Stop the stack, and local Supabase if it runs, keeping their data |
| `make reset` | Stop them and delete their data volumes and Supabase's network, to start from scratch |
| `make smoke` | Check the running stack end to end ([The smoke tests](smoke-tests.md)) |

`make` on its own lists every command; [Makefile targets](../reference/makefile.md) is the same list, with the variables they read.

## Data

Each service keeps its data in a named volume of the `stackr` project: `prometheus-data`, `tempo-data`, `loki-data`, `pyroscope-data`, `grafana-data`, `postgres-data`, `redis-data`, `minio-data`, `clickhouse-data` and `clickhouse-logs`. Local Supabase's volumes are the CLI's. `make down` keeps all of them; `make reset` deletes them, local Supabase's included.

Retention is set for local use: Prometheus keeps 15 days of metrics, and Loki 7 days of logs.
