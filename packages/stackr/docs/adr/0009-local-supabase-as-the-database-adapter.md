# ADR-0009: Local Supabase as the database adapter

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0002](0002-local-supabase-through-its-cli.md) runs local Supabase through its CLI, with the Compose services joining Supabase's network. [ADR-0005](0005-ports-and-adapters-for-the-stack.md) then made the database a port, with local Supabase as the default adapter and plain PostgreSQL as an alternative that must also work, and [ADR-0008](0008-langfuse-and-its-services.md) creates each service's database with `db-init` on either. Implementing Supabase left these open:

- **Names.** The CLI names its containers, volumes and network after the project id, and also labels its containers with it as a Compose project (`com.docker.compose.project`). With the id `stackr`, Compose would treat Supabase's containers as orphans of its own project.
- **The network.** Compose refuses to start a service whose external network doesn't exist, but only for the services it is starting. The CLI creates its network when it's missing and removes it on `supabase stop`, unless the network already existed, in which case it joins it and leaves it alone.
- **Choosing the adapter.** The two adapters differ in host, admin password (Supabase's local one is fixed, `postgres`) and whether the CLI runs.
- **Ports.** The CLI publishes Supabase's ports on every interface, with no setting to bind them to `127.0.0.1` ([ADR-0006](0006-networks-and-published-ports.md)).
- **Architecture.** The CLI's images are multi-architecture, but a `DOCKER_DEFAULT_PLATFORM` set for other work makes Docker run them under emulation, where Supabase's Realtime fails to start.

## Decision

- **The project id is `stackr-supabase`,** so the database is `supabase_db_stackr-supabase` and the network `supabase_network_stackr-supabase`. `scripts/check-config supabase` checks that `supabase/config.toml`, `compose.yaml` and the Makefile agree, and that the id differs from the Compose project's name.
- **The services that use PostgreSQL join Supabase's network,** as ADR-0002 decided: `db-init`, Langfuse and, in phase 4, the gateway. `make up` creates the network when it's missing, before `supabase start`, so:
  - `supabase stop` never removes it from under running services
  - the same Compose file works with the plain PostgreSQL adapter, where the network is simply empty
  - profiles that don't use PostgreSQL (`observability`) start with plain `docker compose`, without it
- **One switch chooses the adapter:** `STACKR_DATABASE=supabase` (the default) or `postgres`, in `.env`. `make` derives the rest: whether to run `supabase start` or add the `postgres` profile, and the host and admin password that `db-init` and the services' connection strings use. Compose's own defaults are Supabase's, so plain `docker compose` works with the default adapter. Supabase starts only when a profile that uses PostgreSQL runs.
- **The CLI is pinned** in `versions.env` (`SUPABASE_CLI_VERSION`). CI installs that version; `make` uses an installed `supabase`, or runs the pinned version through `npx`. The CLI version pins Supabase's own images.
- **Supabase's published ports are the exception to ADR-0006:** they listen on every interface, as the CLI publishes them. SECURITY.md says so.
- **`make` unexports `DOCKER_DEFAULT_PLATFORM`,** so the stack's images always run natively.
- **Lifecycle:** `make down` stops Supabase and keeps its data; `make reset` deletes its volumes and the network. After `supabase db reset` or `supabase stop --no-backup`, which delete the database volume, the next `make up` recreates the stack's databases, empty.

## Options considered

### Connecting the services to Supabase's PostgreSQL

| Option | Plain PostgreSQL adapter | Who owns the network | Supabase's aliases (`db`, `auth`, `storage`) |
|---|---|---|---|
| **The services join Supabase's network, which `make up` creates (chosen)** | Works: the network exists, empty | `make`; the CLI joins it | Only on Supabase's network |
| Supabase joins the `stackr` network (`supabase start --network-id stackr`) | Works | `make`, and every `supabase` command must pass the flag | On the network the libraries' dev containers join |
| The services connect through the host (`host.docker.internal:54322`) | Works | Nobody | Not reachable by name |

### Choosing the adapter

| Option | Settings that must agree |
|---|---|
| **One switch, `STACKR_DATABASE`, with the rest derived by `make` (chosen)** | None |
| Host, admin credentials and profiles set separately in `.env` | Four |

## Consequences

- Easier: the database adapter is one setting, and the same Compose file serves both.
- Easier: Langfuse and the gateway keep their data on Supabase's PostgreSQL, next to the application's.
- Harder: the libraries' dev containers join `stackr` for the stack's services, and also Supabase's network (or use port 54322 on the host) to reach its PostgreSQL by name.
- Harder: with plain `docker compose` and the `postgres` adapter, `STACKR_DB_HOST` and `STACKR_DB_ADMIN_PASSWORD` have to be set by hand; `make` is the supported way.
- Revisit: binding Supabase's ports to `127.0.0.1`, if the CLI gains a setting for it.

## Action items

1. [x] The `supabase/` project, the network, the adapter switch and CI for both adapters (RFC-0001 phase 3).
2. [ ] The gateway's database on the same adapter (phase 4).
