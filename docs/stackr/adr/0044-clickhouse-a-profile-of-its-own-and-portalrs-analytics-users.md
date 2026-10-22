# ADR-0044: ClickHouse, a profile of its own, and portalr's analytics users

**Status:** Accepted
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

Amends [ADR-0031](0031-clickhouses-admin-apart-from-langfuse.md) for [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) (portalr product analytics, [#361](https://github.com/alexnodeland/lattice/issues/361)). ADR-0031 made ClickHouse's users stackr's own, with `admin` and `langfuse`, and ran ClickHouse only for Langfuse. This record lets analytics run without Langfuse, adds portalr's analytics database and its users, and has the backups take that database.

## Context

- **ClickHouse runs only with Langfuse.** The service is under `profiles: [langfuse]` in `compose.yaml`, so analytics could only be on where Langfuse is.
- **ClickHouse has two users,** set in `deploy/clickhouse/users.xml`: `admin`, for operators, from inside the container, and `langfuse`, limited to `default` and six system tables.
- **The backups don't cover a new database.** The single host's and the state host's take `BACKUP DATABASE default, DATABASE stackr_drill` ([ADR-0027](0027-the-single-hosts-backups.md), [ADR-0037](0037-the-state-hosts-clickhouse-backups.md)), and nothing else.
- **Grafana can't read ClickHouse.** It has no ClickHouse datasource.

The owner decided on 2026-10-22 that ClickHouse gets a profile of its own, pulled in by both `langfuse` and `analytics`, so that analytics works without Langfuse.

## Decision

- **ClickHouse is listed under `profiles: [clickhouse, langfuse, analytics]`.** Compose starts a service when any of its profiles is active, as `db-init`'s `[langfuse, gateway, auth]` already does, so:
  - `langfuse` alone still starts ClickHouse, and Langfuse is unchanged;
  - `analytics` alone starts it without Langfuse's containers;
  - `clickhouse` alone is there for an operator.
- **`CLICKHOUSE_PASSWORD`, Langfuse's password, is asked for only where Langfuse runs, and the `langfuse` user is never left with an empty password.** `langfuse` signs in from `::/0`, so an empty password would open ClickHouse to the stack's network. The invariant: where Langfuse is off, either the `langfuse` user isn't made, or it has a generated password no one is given; never an empty one. The first slice picks the Compose expression that keeps it, and the smoke test signs in as `langfuse` with an empty password and is refused, with and without Langfuse.
- **Two users join ADR-0031's, in `users.xml`:**
  - `portalr_analytics_writer`:
    - `INSERT` on `analytics.events`, and nothing else: no `SELECT`, no other database, no system table;
    - its password is `CLICKHOUSE_ANALYTICS_WRITER_PASSWORD`, which `make env` generates.
  - `portalr_analytics`:
    - `SELECT` on `analytics.events`, behind a row policy on the tenant, which RFC-0008's P4 describes and whose pattern phase 0 verifies;
    - a readonly profile;
    - its password is `CLICKHOUSE_ANALYTICS_PASSWORD`.
  - Like ADR-0031's, both passwords are marked `hide_in_preprocessed`, and each user has a quota, so a heavy read can't starve Langfuse.
  - Both sign in only from the stack's internal network, where the application runs: the Compose network's range locally, the state host's private subnet on AWS. Not `::/0`, as `langfuse` does.
- **`langfuse` still reaches only `default`.** It has no grant on `analytics`, and the analytics users have none on `default`.
- **The `analytics` database and its table are made by the first slice,** as `admin`, from an init step that runs before portalr's application starts. portalr's users can't make or alter a table.
- **The backups take `analytics`:** `BACKUP DATABASE default, DATABASE analytics, DATABASE stackr_drill`, on the single host and the state host. A database that doesn't exist yet, where analytics is off, is made empty first, so one statement serves both.
- **The `backup` user's grants grow,** in `deploy/host/clickhouse/backup-user.xml`, which the state host mounts too: `SELECT, BACKUP ON analytics.*` beside today's `SELECT, BACKUP ON default.*`, or the backup statement is refused. That is part of the first slice.
- **The drill restores `analytics` and checks a row count.** Today the drill backs up and restores only `stackr_drill` (`deploy/host/restore-drill`). Restoring `analytics` from the nightly backup into a scratch database needs `backup` to have `ALL` on that scratch database (as it has on `restore_drill` and `restore_sentinel`), and `SELECT` there to count.
- **`langfuse` keeps `SELECT` on `system.query_log`,** which ADR-0031 gave it, so it could read analytics' query text. `query_masking_rules` redact, in any statement that is logged, the tenant setting's value and the literals compared with `tenant_id` or `distinct_id` (one, or an `IN` list), and portalr sends inserts' rows in the request body, not the query text. A test reads `system.query_log` as `langfuse` after an analytics read and insert, and finds no tenant id and no `distinct_id`.
- **Grafana's ClickHouse datasource** is a later phase (RFC-0008, phase 3). Whether the plugin is baked into the image or installed at start is still open there. When it lands, it reads as a `grafana_analytics` user with `SELECT` on `analytics.events` and no row policy, since operators read across tenants (portalr ADR-0005).
- **The smoke test grows:**
  - `langfuse` with an empty password is refused, with Langfuse on and off;
  - with `analytics` alone, ClickHouse starts and Langfuse's containers don't;
  - the writer can insert and can't select;
  - the reader can't read without its tenant setting;
  - `langfuse` is refused `analytics`.

## Options considered

| Option | For | Against |
|---|---|---|
| **A `clickhouse` profile that `langfuse` and `analytics` pull in (chosen)** | Analytics without Langfuse; Langfuse's profile unchanged | One more profile name |
| Analytics needs Langfuse | Nothing to change in Compose | A tenant's adoption depends on an LLM-tracing tool being on |
| A second ClickHouse for analytics | Langfuse's load and analytics' kept apart | Twice the memory, and two of everything to back up |
| **Separate writer and reader users (chosen)** | The relay can't read, and the reader can't write | Two passwords |
| One analytics user | One password | A bug in the relay could read across tenants |

## Consequences

- An operator can run `analytics` without `langfuse`.
- `make env` generates two more passwords, and a deployment upgrading to this record needs them in its `.env`, which `make env` adds.
- The backups grow by the analytics database's size, small next to Langfuse's.
- ADR-0031's smoke test and users file change, and its statement that ClickHouse is Langfuse's alone no longer holds.
- **As built** (the first slice, lattice RFC-0008's "First slice as built"):
  - The two users are in a file of their own, `deploy/clickhouse/analytics-users.xml`, with their profiles and quota. Their row policy is a user-level `<filter>` there. Without the setting, a read fails with `Unknown setting` rather than seeing nothing.
  - The server's settings are in `deploy/clickhouse/analytics.xml`.
  - **The reader is `readonly = 1`,** with `SQL_portalr_tenant` its only `changeable_in_readonly` setting, and fixed limits: it can't lift `max_memory_usage` or `max_execution_time`, so the quota protecting Langfuse holds.
  - **`langfuse` sees only its own rows** of `system.query_log` and `system.processes`, by a row policy in `users.xml`.
  - **Analytics' queries aren't logged:** `log_queries = 0` in both profiles, which the reader can't change and the writer can't by a constraint. The masking rules cover what an operator's statements log.
  - **The empty-password invariant holds by what exists:** `make env` makes `CLICKHOUSE_PASSWORD` whether or not Langfuse runs, and `compose.yaml` keeps requiring it (`:?`), so `langfuse` never has an empty one. The smoke test checks it.
  - ClickHouse's HTTP interface is published on `127.0.0.1` alone, whatever `STACKR_BIND` says, for an application on this machine: Langfuse's user signs in from any address, so ClickHouse is never published beyond the loopback. This amends ADR-0006, which published nothing of ClickHouse's. The single host's overlay keeps it, on the loopback, as every service there is but Caddy, for the smoke test's own reader.
  - The drill checks `restore_analytics` has as many tables as `analytics`; rows written since the backup would make a row count differ.
  - **The AWS recipe's state host doesn't run analytics yet.** Its ClickHouse leaves out the two users and the settings, which `scripts/check-config` names, and its backups are unchanged.
- **With the relay** (lattice RFC-0008's relay slice), the writer may also delete (`GRANT ALTER DELETE ON analytics.events`), for a person's deletion when they take back their yes. That grant lets it delete any row of `analytics.events`, in any tenant: portalr deletes only by a person's hash, but a compromised writer could delete every tenant's events, though never read them. Langfuse's user sees only `default`'s rows of `system.mutations`, since that mutation names the person's hash.
