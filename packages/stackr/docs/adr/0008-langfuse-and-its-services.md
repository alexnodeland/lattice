# ADR-0008: Langfuse and its services

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 plans self-hosted Langfuse with ClickHouse, MinIO and Redis (shared with the gateway), and its database on the stack's PostgreSQL. It was written against Langfuse 3. Since then:

- **Langfuse 4** became generally available for self-hosting (2026-08-17). It keeps Langfuse 3's services (web, worker, PostgreSQL, ClickHouse, Redis, S3) and moves to an observations-first data model. Langfuse 3 receives security fixes only, until January 2027, and new features (the v2 observations and metrics APIs among them) are Langfuse 4 only.
- **MinIO** no longer publishes community images. Langfuse's own Compose file uses Chainguard's free MinIO image, which is published as `latest` only.
- Langfuse's queues need Redis's `noeviction` policy, which applies to the whole server, so sharing it with the gateway's cache has a cost.
- Langfuse and the gateway each need a PostgreSQL database and role, on whichever PostgreSQL is the database adapter ([ADR-0005](0005-ports-and-adapters-for-the-stack.md)): plain PostgreSQL now, local Supabase in phase 3. Supabase's `postgres` role is not a superuser.

## Decision

- **Langfuse 4**, with web and worker pinned to the same exact version and updated together.
- **ClickHouse 26.8**, a long-term support release. Langfuse 4 needs 25.12 or later, and adjusts its query settings for the ClickHouse version it finds.
- **Valkey** implements the Redis protocol, as one server named `redis` shared by Langfuse (database 0) and the gateway (database 1), with `noeviction`. The gateway's cache entries expire by their TTLs, so they don't need eviction. Its password is written to a config file at start, never onto a command line.
- **MinIO from Chainguard's image, pinned by digest,** behind the S3 port. Replacing it with another S3 store is a change of endpoint and credentials. A new digest is found with `docker buildx imagetools inspect cgr.dev/chainguard/minio:latest`.
- **Databases are created by `db-init`,** a psql script (`deploy/postgres/init.sql`) that runs on every start before the services that need it. For each service it creates a role with the password from `.env` (and resets it, so the two stay in step), makes the admin role a member (needed on PostgreSQL 16 and later when the admin isn't a superuser, as on Supabase), and creates the service's database, owned by its role and in UTC. It runs the same way on any PostgreSQL.
- **The Collector sends traces to Langfuse only when the `langfuse` profile runs.** The traces pipeline's exporters come from an environment variable, which `make up` sets from the chosen profiles, so a stack without Langfuse doesn't log export errors.

## Options considered

### Langfuse version

| Option | Support | Features | Migration for a new stack |
|---|---|---|---|
| **Langfuse 4 (chosen)** | Current | All, including the v2 APIs | None |
| Langfuse 3 | Security fixes until January 2027 | No new features | A v3-to-v4 migration later |

### Redis protocol server

| Option | Licence | Supported by Langfuse | Separate cache for the gateway |
|---|---|---|---|
| **Valkey, shared (chosen)** | BSD | Yes, 8 and later | No: database 1 of the same server |
| Redis, shared | AGPLv3 or source-available | Yes | No |
| Two servers | Either | Yes | Yes, with its own eviction policy |

### S3 store

| Option | Maintained | Pinning |
|---|---|---|
| **Chainguard's MinIO (chosen)** | Rebuilt daily | By digest |
| MinIO's last community image | No | By tag |
| Another S3 server (SeaweedFS, RustFS) | Yes | By tag, but not what Langfuse tests with |

### Creating databases

| Option | Runs | Works on hosted PostgreSQL | Idempotent |
|---|---|---|---|
| **An init job on every start (chosen)** | Every `make up` | Yes | Yes |
| Supabase migrations | Only on a new database volume | Would be pushed to a hosted project | `CREATE DATABASE` can't run in a migration's transaction |
| The PostgreSQL image's init scripts | Only on a new volume, and only for the plain PostgreSQL adapter | No | No |

## Consequences

- Easier: a new stack starts on the Langfuse line that receives features, with no migration ahead of it.
- Easier: the same `db-init` provisions databases on plain PostgreSQL, local Supabase or a hosted PostgreSQL.
- Harder: Langfuse 4 reads trace-level attributes (`session.id`, `user.id`, `langfuse.trace.name`, tags) from every span, not only the root; the libraries must set them on each span they own.
- Harder: a MinIO digest bump doesn't show which MinIO release it contains.
- Revisit: a separate cache server for the gateway, if its cache grows large enough to matter under `noeviction`.

## Action items

1. [x] The `langfuse` profile, `db-init` and the Collector's Langfuse route (RFC-0001 phase 2).
2. [ ] The gateway's database and cache on the same services (phase 4).
