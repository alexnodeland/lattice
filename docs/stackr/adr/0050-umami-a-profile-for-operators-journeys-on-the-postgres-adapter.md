# ADR-0050: Umami, a profile for operators' journeys, on the postgres adapter

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

For phase 6 of [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) (portalr product analytics, [#361](https://github.com/alexnodeland/lattice/issues/361)): Umami, as an opt-in profile, fed by portalr's relay. Its replay comes after, behind a review of its own.

## Context

- **Umami** 3.4.0 is MIT. It keeps journeys, and in 3.x replays, in PostgreSQL. Its ingest, `/api/send`, takes events from anyone who can reach it, with no credential. The security review's F4.5 asks that only the application reach it.
- **Umami's session is derived from the distinct id it is given,** as well as from the website, the client's address and its agent: `uuid(sourceId, ip, userAgent, sessionSalt, distinctId)` in `src/app/api/send/route.ts` at v3.4.0. So events relayed from one address, with one agent, still fall into a session per distinct id. The smoke test checks this against the running Umami, and checks that deleting one person's session leaves another's.
- **The stack's services share networks:** `stackr` for all of them, and local Supabase's network for those that use its database. A service on the same network as Umami could post to its ingest.

## Decision

- **An `umami` profile,** off by default, running `ghcr.io/umami-software/umami:3.4.0@sha256:85909afc…f367`, which is the multi-architecture index (amd64 and arm64).
  - Telemetry and update checks are off.
  - Its bot check is off, since every event comes from portalr's relay, with portalr's own user agent.
- **It runs on the postgres adapter alone,** and the profile brings plain PostgreSQL up with it, as `langfuse`, `gateway` and `auth` do: `umami` is among the Makefile's `DATABASE_USERS`. `scripts/check-make` checks that `make up PROFILES=umami` starts the `postgres` profile.
  - `make up` refuses the profile beside local Supabase, and says why: Supabase's database sits on a network the stack's other services share, so Umami could only reach it by sharing that network too, which F4.5 rules out. `scripts/check-make` tests the refusal.
  - Its data is in PostgreSQL: a database `umami`, owned by the role `umami`, that no other role may connect to (`REVOKE CONNECT … FROM PUBLIC`), whose tables are in the schema `umami`, the only schema there.
  - `umami-db-init`, a service of the profile's own, makes them from `deploy/postgres/umami.sql`, so they are made only with the profile, with or without `make`. The smoke test checks that the role is refused in the server's own database.
- **Three networks of its own, and none shared with the stack's other services:**
  - `stackr-umami`, internal, is the ingest. `make up` creates it whenever it starts, whatever the profiles, since every application the template makes with the portal declares it as external. It refuses to start if a network by that name exists and isn't internal, and `scripts/check-make` tests that. The application joins it, so it is the application's alone, with `umami-init`, which exits.
  - `umami-db`, internal, holds plain PostgreSQL and Umami.
  - `umami-ui` publishes its port, for operators, on `127.0.0.1:${UMAMI_PORT:-3400}`, whatever `STACKR_BIND` says. That holds on one machine and on the single host, which operators reach by an SSH tunnel, as Grafana.
  - **That port is the ingest's too.** Umami serves its UI and `/api/send` on one port. So anything on the machine itself may post events to it; nothing off the machine can. "Only the application reaches the ingest" holds for the stack's containers, not for the machine's own processes. The smoke test asserts this limit, so a change to it is seen.
  - The AWS recipe runs no Umami, and `scripts/check-config aws` fails if anything of the recipe names it.
- **`umami-init`** runs after Umami is up, as `clickhouse-init` does, and is idempotent. `.env` is the source of truth for each password, and `make env` generates every secret.
  - It gives the admin `UMAMI_ADMIN_PASSWORD` in place of Umami's first password. A password changed in Umami's UI since is refused with a message saying so, until `.env` names it.
  - It makes portalr's user, with a fixed id. Where `UMAMI_PORTALR_PASSWORD` was rotated in `.env`, the admin gives the user the new one.
  - It makes portalr's website, owned by that user, with the fixed id `UMAMI_WEBSITE_ID`.
  - Passwords go in request bodies, escaped as JSON, and tokens in a header file, never on a command line.
  - Until it has run, Umami's first admin login, `admin` / `umami`, works. `make up` runs it at once. Someone who starts the profile with plain `docker compose --profile umami up` must run `umami-init` too, before anyone else on the machine reaches the loopback port.
- **Checks:** the smoke test, in CI's single-host row, checks that:
  - the applications' network can post to the ingest, and the stack's network can't;
  - the UI answers on the loopback, and takes events there, as stated above;
  - Umami's role is refused outside its database;
  - portalr's client keeps a session per person and deletes one person's alone, against the running Umami;
  - with the analytics profile, portalr's relay works end to end: a yes copies a batch to Umami, and a no deletes it there.

## Options considered

- **Umami on local Supabase's network,** or on `stackr`: the stack's other services could post to its ingest.
- **Umami bound to the ingest network's address alone,** on any adapter: it rests on Docker choosing that address for the published port, which needs `gw_priority`, a newer Compose than the stack asks for.
- **A PostgreSQL of its own:** heavier. A database and a role of its own are enough.

## Consequences

- Journeys are for deployments on the postgres adapter, which every single host is.
- PostgreSQL shares `umami-db` with Umami, so it could reach Umami; it runs no client of it.
- An operator reads every tenant's journeys in Umami's UI, as Grafana's dashboards show every tenant's. Umami has no tenants.
