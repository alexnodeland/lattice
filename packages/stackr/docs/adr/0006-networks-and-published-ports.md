# ADR-0006: Networks and published ports

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

The stack's services talk to each other, to local Supabase (whose containers the Supabase CLI manages outside Compose), and to applications: the libraries' dev containers, applications in the `app` profile, and processes on the host. Developers' machines already run other stacks, whose ports stackr must not collide with, and a single host may be reachable from a network it shouldn't expose the stack to.

## Decision

- **One Compose network with a fixed name, `stackr`.** Services reach each other by service name. Containers outside the project (the libraries' dev containers, other applications) join it as an external network and use the same names, such as `otel-collector:4317`.
- **Local Supabase keeps its own network,** and only the services that use its PostgreSQL join it as well ([ADR-0002](0002-local-supabase-through-its-cli.md)).
- **Every published port binds to `STACKR_BIND`,** `127.0.0.1` by default, so nothing is reachable from other machines unless someone chooses it.
- **Every published port is a setting in `.env`,** with a default:
  - the ports applications send to keep their standard numbers: OTLP on 4317 (gRPC) and 4318 (HTTP), Pyroscope on 4040
  - the user interfaces and APIs keep their usual numbers where they don't collide: Grafana 3000, Prometheus 9090, Tempo 3200, Loki 3100
  - where two services share a usual number, or it is commonly taken, one moves; those choices are listed in the architecture document as the services land
- **Services that nothing outside the stack uses** (ClickHouse, Redis, internal APIs) are not published.

## Options considered

| Option | Collisions with other stacks | Exposure | Reachable from other containers |
|---|---|---|---|
| **Fixed network, ports bound to 127.0.0.1 and configurable (chosen)** | Avoidable with one setting | This machine only, by default | By name, on `stackr` |
| Compose defaults (a generated network, ports on every interface) | Fixed numbers collide | Every interface | Only through published ports |
| No published ports; everything through a reverse proxy | None but the proxy's | Chosen per route | By name |

## Consequences

- Easier: an application or dev container anywhere on the machine sends telemetry to `otel-collector:4317` on the `stackr` network, or to `localhost:4317` from the host.
- Easier: a port that collides is one line in `.env`.
- Harder: the `stackr` network name is a contract with the libraries' dev containers, so renaming it is a breaking change.
- Revisit: a reverse proxy with names instead of ports, if the list of published ports keeps growing.

## Action items

1. [x] Publish the observability services this way (RFC-0001 phase 1).
