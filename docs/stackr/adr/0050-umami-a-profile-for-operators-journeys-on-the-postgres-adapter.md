# ADR-0050: Umami, a profile for operators' journeys, on the postgres adapter

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

For phase 6 of [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) (portalr product analytics, [#361](https://github.com/alexnodeland/lattice/issues/361)): Umami, as an opt-in profile, fed by portalr's relay. Its replay comes after, behind a review of its own.

## Context

- **Umami** 3.4.0 is MIT. It keeps journeys, and in 3.x replays, in PostgreSQL. Its ingest, `/api/send`, takes events from anyone who can reach it, with no credential. The security review's F4.5 asks that only the application reach it.
- **The stack's services share networks:** `stackr` for all of them, and local Supabase's network for those that use its database. A service on the same network as Umami could post to its ingest.

## Decision

- **An `umami` profile,** off by default, running `ghcr.io/umami-software/umami:3.4.0@sha256:85909afc…f367`, which is the multi-architecture index (amd64 and arm64).
  - Telemetry and update checks are off.
  - Its bot check is off, since every event comes from portalr's relay, with portalr's own user agent.
- **It runs on the postgres adapter alone.**
  - `make up` refuses the profile beside local Supabase, and says why: Supabase's database sits on a network the stack's other services share, so Umami could only reach it by sharing that network too, which F4.5 rules out. `scripts/check-make` tests the refusal.
  - Its data is in PostgreSQL: a database `umami`, owned by the role `umami`, whose tables are in the schema `umami`, the only schema there.
  - db-init makes them only where `make up` chose the profile. The smoke test checks that the role is refused in the server's own database.
- **Three networks of its own, and none shared with the stack's other services:**
  - `stackr-umami`, internal, is the ingest. `make up` creates it whenever it starts, and the template's application joins it, so it is the application's alone (with `umami-init`, which exits).
  - `umami-db`, internal, holds plain PostgreSQL and Umami.
  - `umami-ui` publishes its port, `127.0.0.1:${UMAMI_PORT:-3400}`, for operators. It is on the loopback on one machine, and on the single host too, reached by an SSH tunnel as Grafana is. The AWS recipe runs no Umami.
- **`umami-init`** runs after Umami is up, as `clickhouse-init` does, and is idempotent. It gives the admin `UMAMI_ADMIN_PASSWORD` in place of Umami's first password, and makes portalr's user and portalr's website, owned by that user, with the fixed id `UMAMI_WEBSITE_ID`. `make env` generates every secret.
- **Checks:** the smoke test, in CI's single-host row, checks that the applications' network can post to the ingest and the stack's network can't, and that the UI answers on the loopback.

## Options considered

- **Umami on local Supabase's network,** or on `stackr`: the stack's other services could post to its ingest.
- **Umami bound to the ingest network's address alone,** on any adapter: it rests on Docker choosing that address for the published port, which needs `gw_priority`, a newer Compose than the stack asks for.
- **A PostgreSQL of its own:** heavier. A database and a role of its own are enough.

## Consequences

- Journeys are for deployments on the postgres adapter, which every single host is.
- PostgreSQL shares `umami-db` with Umami, so it could reach Umami; it runs no client of it.
- An operator reads every tenant's journeys in Umami's UI, as Grafana's dashboards show every tenant's. Umami has no tenants.
