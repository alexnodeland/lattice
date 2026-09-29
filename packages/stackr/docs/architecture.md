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
