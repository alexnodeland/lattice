# Architecture

> **Status:** accepted design, being built in the phases tracked by [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). This document is evergreen: it is updated in the same pull request as the change it describes, and the table below shows what exists today. Decisions are recorded in [`adr/`](adr/README.md), and proposals in [`rfcs/`](rfcs/README.md).

| Part | Status |
|---|---|
| Foundation: layout, `make`, generated secrets, static validation in CI | Implemented |
| `observability` profile: OpenTelemetry Collector, Prometheus, Tempo, Loki, Pyroscope, Grafana | Implemented |
| `langfuse` profile: Langfuse web and worker, ClickHouse, Valkey, MinIO | Implemented |
| Local Supabase, through its CLI: the default database adapter | Implemented |
| `postgres` profile: plain PostgreSQL, the alternative database adapter | Implemented |
| `gateway` profile: the LiteLLM proxy, with a team per tenant | Implemented |
| The application template (Copier) and the `app` profile | Implemented |
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
| LLM gateway | OpenAI-compatible HTTP API, with models named by alias or group | `LITELLM_BASE_URL`, `LITELLM_API_KEY`; `OPENAI_BASE_URL`, `OPENAI_API_KEY` for OpenAI SDKs | The LiteLLM proxy | Implemented |
| Database | A PostgreSQL connection string | `DATABASE_URL` | Local Supabase's PostgreSQL; plain PostgreSQL as the alternative | Implemented |
| Object storage | The S3 API | `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_FORCE_PATH_STYLE` | MinIO | Implemented |
| Identity | JWTs, verified against the issuer's key set (or a shared secret, for HS256) | `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`; `AUTH_JWT_SECRET`, `AUTH_TENANT_CLAIM` | Supabase Auth | Implemented |
| Evaluation data | Langfuse's public API, for scores and datasets | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Self-hosted Langfuse | Implemented |

The settings are a contract with the libraries' extras and the application template, which generates applications wired to these ports only. The stack's own services use the same ports: Langfuse and the gateway reach PostgreSQL, S3 and the Redis protocol through settings in `.env`, and the gateway sends its telemetry to the Collector, so their adapters can change as well. Profiles and evaluation data are the two narrow ports: profiles go to Pyroscope directly until OTLP profiles are stable in the Collector, and Langfuse's API carries scores and datasets, never traces.

## Layout

```
compose.yaml        the stack: one Compose project, with profiles
copier.yml          the application template's questions; its files are in template/
template/           the application template (Copier): an application on artifactr, reflexr or both
.env.example        settings and placeholders; `make env` turns it into .env
versions.env        versions pinned outside compose.yaml: the Supabase CLI, the libraries' dashboards
deploy/<service>/   each service's configuration, mounted read-only
deploy/postgres/    init.sql: each service's role and database, created by db-init
supabase/           the Supabase CLI project: config.toml (project id stackr-supabase) and seed.sql
scripts/            setup-env, validate, smoke, fetch-dashboards, check-config and check-template, run by make and CI
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
    app -- "OpenAI API + traceparent" --> litellm["litellm"]
    litellm -- "OTLP HTTP" --> collector
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
- The gateway adds `gen_ai_client_token_usage`, `gen_ai_usage_cost_USD` and `gen_ai_client_operation_duration_seconds` (histograms, with `job="litellm"`), labelled by model, provider and the tenant's team (`metadata_user_api_key_team_id`).

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

## The gateway profile

The LiteLLM proxy is the LLM gateway port: an OpenAI-compatible API at <http://localhost:4400> (`litellm:4000` on the network) in front of the providers and local model servers ([ADR-0010](adr/0010-the-llm-gateway.md)). Its configuration is `deploy/litellm/config.yaml`.

| Model name | Routes to | Falls back to |
|---|---|---|
| `default` | Claude Sonnet | `gpt-4o`, then `gemini-2.5-pro` |
| `fast` | Claude Haiku | `gpt-4o-mini`, then `gemini-2.5-flash` |
| `claude-sonnet`, `claude-opus`, `claude-haiku` | Anthropic | |
| `gpt-4o`, `gpt-4o-mini` | OpenAI | |
| `gemini-2.5-pro`, `gemini-2.5-flash` | Gemini | |
| `openrouter/<vendor>/<model>` | Any OpenRouter model | |
| `lmstudio`, `omlx/<model>` | LM Studio and oMLX on this machine, through `host.docker.internal` (`LM_STUDIO_API_BASE`, `OMLX_API_BASE`) | |

- **Provider keys** (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`) go in `.env`. A missing one fails only the requests that need it, and the router falls back.
- **Tenants:** each tenant is a team, `tenant-<name>`, with a budget per period (calendar-aligned: `30d` resets on the 1st) and optional rate limits and model list. `make tenant NAME=acme` (or `scripts/create-tenant acme --max-budget 20 --rpm-limit 60`) creates the team and a key, and prints the settings an application reads: `LITELLM_BASE_URL` and `LITELLM_API_KEY`. Running it again keeps the team and creates a key only for a new `--key-alias`. The master key (`LITELLM_MASTER_KEY`) only administers the proxy; the admin UI is at <http://localhost:4400/ui>, as `admin` with the master key.
- **Guardrails,** chosen per request with `"guardrails": ["pii-mask"]` in the request body:

  | Name | What it does |
  |---|---|
  | `pii-mask` | Masks email addresses, US phone and social security numbers, card numbers, and AWS and GitHub credentials before the request reaches the model |
  | `prompt-injection` | Blocks jailbreak, system-prompt and data-exfiltration attempts, with HTTP 400 naming the guardrail |

  The response header `x-litellm-applied-guardrails` lists the guardrails that ran. Attaching guardrails to a team or key needs an Enterprise licence, so the libraries choose them per request, from each workspace's or rule's policy.
- **Telemetry:** the proxy continues the caller's trace from its `traceparent` header, so one trace runs from the application through the proxy to the model call, in Tempo and Langfuse. Prompts and responses are not put on spans. Its metrics carry the tenant's team, not per-key ids. Both are on when the `observability` profile runs.
- **State:** its database `litellm` on the database adapter, created by `db-init`; routing state and a 10-minute response cache in database 1 of the shared Valkey.

## The database

The stack's services keep their data in PostgreSQL through the database port. One setting in `.env`, `STACKR_DATABASE`, chooses the adapter, and `make` derives the rest ([ADR-0009](adr/0009-local-supabase-as-the-database-adapter.md)):

| `STACKR_DATABASE` | Adapter | Started by | Host on the network | Admin | Published port |
|---|---|---|---|---|---|
| `supabase` (default) | Local Supabase's PostgreSQL | `make up`, through the Supabase CLI | `supabase_db_stackr-supabase` | `postgres`, with Supabase's fixed local password `postgres` | 54322 |
| `postgres` | Plain PostgreSQL, the `postgres` profile | `make up`, through Compose | `postgres` | `postgres`, with `POSTGRES_ADMIN_PASSWORD` from `.env` | 55432 |

- **Supabase starts with the profiles that need it:** `make up` runs `supabase start` when a profile that keeps data in PostgreSQL (`langfuse`, `gateway`) is chosen. `make up PROFILES=observability` leaves it off.
- **`db-init`** runs `deploy/postgres/init.sql` with `psql` on every start, before the services that need it. For each service (Langfuse and the gateway) it creates a login role with the password from `.env`, resets the password so the two stay in step, and creates the service's database, owned by its role and in UTC. On Supabase, whose `postgres` role is not a superuser, it first grants itself the role, which PostgreSQL 16 and later require for creating a database owned by it.
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

## The application template

A Copier template generates an application on artifactr, reflexr or both, wired to the stack's ports only ([ADR-0004](adr/0004-the-application-template.md), [ADR-0011](adr/0011-the-application-template-in-detail.md)). Its questions are in `copier.yml` at the repository's root, and its files in `template/`:

```bash
uvx copier copy gh:alexnodeland/stackr my-app    # or a path to a clone of stackr
cd my-app && make install && make env && make check
uvx copier update                                # later: the template's improvements
```

| Question | Default | What it decides |
|---|---|---|
| `project_name`, `project_slug`, `description` | My App, `my-app` | The distribution, the package (`my_app`), the OpenTelemetry service and the Compose project |
| `libraries` | `both` | `artifactr`, `reflexr`, or both side by side on one database and one telemetry setup |
| `evals` | yes | An `evals/` directory with starter evalr experiments |
| `python_version` | 3.12 | 3.12, 3.13 or 3.14 |
| `app_port` | 8800 | The port the application is published on |
| `artifactr_rev`, `reflexr_rev`, `evalr_rev` | Each library's `main` when the template was last updated | The git revision `[tool.uv.sources]` pins, since the libraries aren't on PyPI |

A generated application:

| Part | Where | What |
|---|---|---|
| Surfaces | `app.py`, `collaboration.py`, `automation.py` | FastAPI with each library's REST and WebSocket routes and MCP server under its name: `/artifactr/v1`, `/artifactr/mcp/`, `/reflexr/v1`, `/reflexr/mcp/`; the reactor runs while the application is up |
| Examples | `notes.py`, `tickets.py` | A `note` artifact type, its agent and a `rating` of turns; `ticket.opened` and `ticket.triaged` events, a `triage` rule, its agent, and a `triage-review` of runs |
| Identity | `auth.py` | Supabase's access tokens, verified against its published keys (`AUTH_JWKS_URL`), or with a legacy HS256 secret (`AUTH_JWT_SECRET`); the user is `sub`, the tenant `app_metadata.tenant_id`; anything else is 401, the MCP servers included |
| Database | `database.py` | The libraries' SQL storage on `DATABASE_URL`, migrated at startup, in a schema of the application's own (`DATABASE_SCHEMA`), since Supabase's Data API serves `public` |
| Telemetry | `telemetry.py` | `configure_telemetry`, when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; Langfuse's client, when `LANGFUSE_PUBLIC_KEY` is set, for trace attributes and scores, while traces reach Langfuse through the Collector |
| Gateway | `gateway.py` | Agents on `litellm_model("default")` with `LiteLLMGateway`: each request with its tenant's key and the `pii-mask` and `prompt-injection` guardrails |
| Feedback | `scores.py` | A `FeedbackMirror` to Langfuse scores for each workspace the application uses, and the score configs, created at startup |
| Evals | `evals/` | The agents on a few examples, judged by evaluators of the feedback types: offline with a scripted model (`make evals`), or in Langfuse with the gateway's model (`make evals-langfuse`) |
| Quality gates | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml` | uv, ruff, pyright in strict mode, pytest with warnings as errors and 100% branch coverage, Conventional Commits; tests need no network or stack |
| The `app` profile | `compose.yaml`, `Dockerfile`, `.env.example` | The application beside the stack (`make up`), on the `stackr` network and local Supabase's, where it reaches the stack's services by name |
| Dev container | `.devcontainer/` | Joins the stack's networks when the stack is running |

## Commands

| Command | What it does |
|---|---|
| `make env` | Create or update `.env`, generating local secrets; re-running keeps existing values |
| `make up` | Start the stack, or the profiles named in `PROFILES` (`make up PROFILES=observability`), with local Supabase or the `postgres` profile when they need a database |
| `make down` / `make reset` | Stop the stack and local Supabase, keeping or deleting their data volumes |
| `make dashboards` | Download the libraries' dashboards at the releases pinned in `versions.env` |
| `make tenant NAME=acme` | Create a tenant's team and key on the gateway |
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
- the gateway's configuration, which has no validator of its own: fallbacks name existing model groups, guardrails use open-source integrations and valid modes, every `os.environ/` reference is set in `compose.yaml`, and no key is in the file
- the application template, rendered in every variant (`scripts/check-template`): nothing is left unrendered, and the generated Python, YAML, shell scripts and Compose file pass ruff (with the generated project's settings), yamllint, shellcheck and `docker compose config`
- the scripts, with shellcheck and ruff

CI's **template** job generates each of the six variants (three choices of libraries, with and without evals), and the largest again on Python 3.14, and runs its `make check`: lint, strict types, and its tests with 100% coverage.

**With containers,** the smoke job starts each profile and runs `scripts/smoke`: `observability` alone, and everything on each database adapter. For `observability`, it sends a trace, a metric and a log through the Collector with `telemetrygen`, and finds:

- the trace in Tempo, by a TraceQL search on the run's id
- the metric in Prometheus as `stackr_smoke_total`, which also checks the name translation above
- the log in Loki
- Tempo's span metrics, and the Collector's own metrics, in Prometheus
- Grafana's four data sources healthy, and the Collector dashboard provisioned

For the database adapter, it queries over `db-init`'s own connection that Langfuse's database exists, and with local Supabase that its API answers. For `langfuse` (with `observability`), it sends a trace with a known id to the Collector's HTTP port and finds it in Langfuse through the public API (`/api/public/v2/observations`) and in Tempo, which checks the Collector's route and credentials and Langfuse's ingestion end to end.

For `gateway`, it checks that the proxy loaded both guardrails and both model groups, then creates a key on the `stackr-smoke` team (the only one allowed mocked responses) and sends a mocked request with a `traceparent`: it must be routed to `default`, masked by `pii-mask` and priced, the key's spend must be recorded, `prompt-injection` must block an injection, and the proxy's spans must continue the caller's trace in Tempo and Langfuse. No provider key is needed.
