# Architecture

> **Status:** accepted design, being built in the phases tracked by [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). This document is evergreen: it is updated in the same pull request as the change it describes, and the table below shows what exists today. Decisions are recorded in [`adr/`](adr/README.md), and proposals in [`rfcs/`](rfcs/README.md).

| Part | Status |
|---|---|
| Foundation: layout, `make`, generated secrets, static validation in CI | Implemented |
| `observability` profile: OpenTelemetry Collector, Prometheus, Tempo, Loki, Pyroscope, Grafana | Planned (phase 1) |
| `langfuse` profile: Langfuse web and worker, ClickHouse, Redis, MinIO | Planned (phase 2) |
| Local Supabase, through its CLI | Planned (phase 3) |
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
| Telemetry | OTLP to the Collector: gRPC 4317, HTTP 4318 | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | The Collector, exporting to Tempo, Prometheus, Loki and Langfuse | Planned (phases 1 and 2) |
| Profiles | Pyroscope's push API | `PYROSCOPE_SERVER_ADDRESS` | Pyroscope | Planned (phase 1) |
| LLM gateway | OpenAI-compatible HTTP API, with models named by alias or group | `LITELLM_BASE_URL`, `LITELLM_API_KEY`; `OPENAI_BASE_URL`, `OPENAI_API_KEY` for OpenAI SDKs | The LiteLLM proxy | Planned (phase 4) |
| Database | A PostgreSQL connection string | `DATABASE_URL` | Local Supabase's PostgreSQL; plain PostgreSQL as the alternative | Planned (phase 3) |
| Object storage | The S3 API | `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_FORCE_PATH_STYLE` | MinIO | Planned (phase 2) |
| Identity | JWTs, verified against the issuer's key set | `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE` | Supabase Auth | Planned (phase 5) |
| Evaluation data | Langfuse's public API, for scores and datasets | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Self-hosted Langfuse | Planned (phase 2) |

The settings are a contract with the libraries' extras and the application template, which generates applications wired to these ports only. Profiles and evaluation data are the two narrow ports: profiles go to Pyroscope directly until OTLP profiles are stable in the Collector, and Langfuse's API carries scores and datasets, never traces.

## Layout

```
compose.yaml        the stack: one Compose project, with profiles
.env.example        settings and placeholders; `make env` turns it into .env
scripts/            setup-env and validate, run by make and CI
docs/               this document, ADRs and RFCs
```

As the phases land, each service's configuration goes in `deploy/<service>/`, mounted read-only, and the Supabase CLI project in `supabase/`.

## Conventions

- **One Compose project, named `stackr`,** with profiles, so only what a task needs runs ([ADR-0001](adr/0001-compose-first-with-profiles.md)).
- **A fixed network name, `stackr`.** The libraries' dev containers and applications join it as an external network and reach every service by name.
- **Published ports bind to `STACKR_BIND`,** `127.0.0.1` by default, so the stack is reachable from this machine only.
- **Images are pinned** to versions, and Dependabot proposes updates.
- **Secrets are generated** into a gitignored `.env` by `scripts/setup-env`. `.env.example` holds only settings and placeholders. Compose fails when a required value is missing, rather than starting a service with an empty secret.

## Commands

| Command | What it does |
|---|---|
| `make env` | Create or update `.env`, generating local secrets; re-running keeps existing values |
| `make up` | Start the stack, or the profiles named in `PROFILES` |
| `make down` / `make reset` | Stop the stack, keeping or deleting its data volumes |
| `make validate` | Check every configuration without starting containers |

## Validation

CI runs `scripts/validate`, the same script as `make validate`, on every pull request. It checks without starting containers:

- every YAML file with yamllint
- the Compose configuration for each profile on its own and for all of them together, failing on warnings
- the Grafana dashboards as JSON
- the scripts, with shellcheck and ruff
