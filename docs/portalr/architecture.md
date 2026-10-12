# Architecture

portalr's design is [lattice RFC-0002](../rfcs/0002-portalr-the-portal.md), and its plan [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). Its decisions are in [`adr/`](adr/README.md). This page describes what exists.

## The parts

| Part | Holds |
|---|---|
| `portalr.actions` | portalr's catalog: `portalr:read_telemetry`, `portalr:read_spend` and `portalr:read_deployment`, for `Grants(catalogs=...)` |
| `portalr.tenant` | `Tenant`, which only `allowed()` makes, and only the router calls it, after grantr allows the read |
| `portalr.readers` | One reader per tool: `Tempo`, `Loki`, `Prometheus` (through prom-label-proxy), `Langfuse` and `LiteLLM`, and `Grafana` for operators' deep links. `Readers` holds those the stack runs. The only code that talks to the tools |
| `portalr.invites` | `Invite`, and `SupabaseInvite` over Supabase Auth's admin API |
| `portalr.fastapi` | `portalr_router`, its `Site` settings, the UIs' serving, and its OpenAPI document |
| `web/` | The Bun workspace: `client`, `ui`, `app` and `admin` ([ADR-0008](adr/0008-the-bun-workspace-runs-in-bun.md)) |

## The router

An application mounts `portalr_router(resolve_actor=, grants=, readers=, invite=, site=)` at `/portalr` ([ADR-0011](adr/0011-the-router-and-its-readers.md)).

| Route | Answers | Needs |
|---|---|---|
| `/portalr/app/`, `/portalr/admin/` | The built UIs: hashed assets cached for good, the index for every client-side route, a strict Content-Security-Policy | Nothing |
| `GET /portalr/config.json` | Supabase's URL and publishable key, the surfaces' paths, and which tools are configured | Nothing |
| `GET /portalr/v1/traces`, `/traces/{id}` | The tenant's traces, a session's or a run's, and one trace's spans, from Tempo | `portalr:read_telemetry` |
| `GET /portalr/v1/logs` | The tenant's logs, a thread's or a run's, from Loki | `portalr:read_telemetry` |
| `GET /portalr/v1/metrics` | `turn_latency` or `failed_runs` over time, from Prometheus through prom-label-proxy | `portalr:read_telemetry` |
| `GET /portalr/v1/scores` | The tenant's feedback and evaluation scores, from Langfuse | `portalr:read_telemetry` |
| `GET /portalr/v1/spend` | The tenant's spend against its budget, from its LiteLLM team | `portalr:read_spend` |
| `GET /portalr/v1/deployment/tenants` | Every tenant, and their spend from one LiteLLM team list | `portalr:read_deployment` |
| `GET /portalr/v1/deployment/links` | Deep links into Langfuse and Grafana | `portalr:read_deployment` |
| `POST /portalr/v1/invites` | Invites someone through Supabase Auth, and adds them to the tenant in grantr | `grantr:add_member` |

Each read names its tenant with `X-Tenant`. Each answers `ok`, `unavailable` or `unconfigured`, so a tool that is down fails only its own read. `schemas/portalr.openapi.json` is the routes' document, and a test holds it to the router.

## The readers

Each reader takes a `Tenant` and typed parameters, and builds its query with the tenant first:

| Tool | The tenant, in every query |
|---|---|
| Tempo | `span.tenant.id`, in TraceQL. A trace read by its id is the tenant's only if one span names it and none names another |
| Loki | `tenant_id`, the structured metadata the collector's `tenant.id` becomes |
| Prometheus | prom-label-proxy's `tenant_id` parameter, which rewrites every selector |
| Langfuse | The traces' `tenant:<id>` tag |
| LiteLLM | The tenant's team, `tenant-<id>` |

`tests/readers/test_queries.py` builds every query each reader can send, and fails if one lacks its tenant.
