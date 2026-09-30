# ADR-0021: SQL storage with one dialect-neutral implementation

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0005](0005-one-event-log-per-workspace.md)

## Context

RFC-0001 phase 4 builds `SqlStorage`, the production implementation of the storage protocol ([ADR-0019](0019-storage-protocol-and-workspace-handles.md)), on SQLAlchemy 2 async and Alembic. The protocol fixes what storage must guarantee. Building it settled how:

- How a transaction is serialized with the others on its workspace when several processes share a database, on both PostgreSQL and SQLite.
- How a subscription learns about envelopes that other processes commit. [ADR-0005](0005-one-event-log-per-workspace.md) planned PostgreSQL `LISTEN/NOTIFY`, with polling on SQLite.
- How entities are stored, given that artifact types are the application's own Pydantic models and change without artifactr's involvement.
- How the schema is created and upgraded next to the application's own tables and migrations.
- How the 100% coverage gate ([ADR-0015](0015-quality-gates.md)) is met, when the main test jobs have no PostgreSQL.

## Decision

- **One dialect-neutral implementation.** Nothing in `SqlStorage` depends on the database dialect. What differs lives in engine setup: engines from `create_sqlite_engine` begin every transaction with `BEGIN IMMEDIATE`. The suite covers every line on SQLite alone, and a separate CI job runs it on PostgreSQL.
- **A transaction locks its workspace's row as it begins.** It creates the row if the workspace is new, then selects it `FOR UPDATE` before it loads anything. If two transactions create the same row at once, the losing insert fails inside a savepoint and that transaction locks the winner's row instead. `save` assigns `seq` from the locked row's `head_seq`. SQLite ignores `FOR UPDATE`, and `BEGIN IMMEDIATE` takes the database's write lock instead. PostgreSQL must run at its default `READ COMMITTED` isolation.
- **Subscriptions poll, and wake early for local commits.** `subscribe` reads the log a page at a time. Once it has caught up, it waits for a commit made through the same `SqlStorage`, or for `poll_interval` (0.5 s by default), whichever comes first. v0.1 does not use `LISTEN/NOTIFY`; it stays open as an optimisation.
- **Entities are JSON documents, with a few columns beside them.** Each entity is stored as its Pydantic model's JSON (`model_dump(mode="json")`) and rebuilt with `load_versioned` or `model_validate`. The columns beside it are the ones reads filter and order by: kind, archived, status and thread. The column type is `JSON`, not PostgreSQL's `JSONB`, because `JSONB` reorders object keys, and dicts in artifact data are ordered.
- **Every primary key starts with the tenant and the workspace**, and every query filters on both. Lists come back oldest first, by a creation position taken from a counter on the locked workspace row.
- **Leases are rows.** A lease is taken with one conditional `UPDATE` (the holder renewing it, or anyone once it has expired), or else an `INSERT`. An insert that collides with the primary key means another holder has the lease.
- **Migrations ship in the package.** `migrate(engine)` runs the packaged Alembic scripts up to the latest revision. They record their version in their own table (`artifactr_alembic_version`), and every table name starts with `artifactr_`, so they sit beside the application's schema and migrations. `create_schema(engine)` creates the tables straight from the models, for tests and prototypes. A test runs the migrations on both databases and checks that Alembic's autogenerate finds no differences from the models.
- **Drivers are extras.** `artifactr[sql]` installs SQLAlchemy and Alembic. `artifactr[postgres]` adds asyncpg, and `artifactr[sqlite]` adds aiosqlite. The library imports neither driver.

### Amendment (2026-09-29): a SQLite engine keeps one connection

Under load, SQLite transactions in one process failed with "database is locked": each held its own connection and polled for the write lock through SQLite's busy handler, which gives up after `sqlite3`'s five-second `timeout` and keeps no order. reflexr had already decided otherwise (its ADR-0030).

- **`create_sqlite_engine` pools a single connection** unless given another `poolclass`. SQLite runs one transaction at a time anyway, so a process's transactions queue for the connection and take turns in the order they begin, as on in-memory storage, for up to the pool's `pool_timeout` (30 seconds). Only other processes contend for the write lock.

## Options considered

### Serializing the transactions on a workspace

| Option | Across processes | Dialect-specific code | Cost |
|---|---|---|---|
| **Lock the workspace row with `SELECT … FOR UPDATE` (chosen)** | Yes | None in storage; SQLite's engine begins immediately | One locked row per transaction |
| PostgreSQL advisory locks | Yes | PostgreSQL only | Needs a second mechanism for SQLite |
| `SERIALIZABLE` isolation with retries | Yes | Retryable errors differ by driver | Every commit must be ready to retry |
| An in-process lock | No | None | Wrong as soon as there are two replicas |

### Following the log from other processes

| Option | Latency across processes | Works on SQLite | Complexity |
|---|---|---|---|
| **Polling, plus an in-process wake-up (chosen)** | Up to `poll_interval` | Yes | Low: one query per interval for each caught-up subscription |
| PostgreSQL `LISTEN/NOTIFY` | Immediate | No, so polling is needed anyway | A dedicated connection, reconnection, and a dialect branch |
| An external broker (Redis, NATS) | Immediate | Yes | A new infrastructure dependency |

### Storing entities

| Option | When an application's type changes | Queryable | Fidelity |
|---|---|---|---|
| **JSON documents plus filter columns (chosen)** | Nothing to migrate | By the columns artifactr needs | Exact |
| A table, or columns, per artifact type | A migration per change | Fully | Exact |
| `JSONB` documents | Nothing to migrate | Inside documents too, with indexes | Object keys are reordered |

### Creating and upgrading the schema

| Option | Upgrades existing databases | Beside the application's own Alembic |
|---|---|---|
| **Packaged migrations with their own version table (chosen)** | Yes | Yes |
| `metadata.create_all` only | No | Yes, but every schema change is left to the application |
| Migrations the application copies into its own history | Yes | Yes, but each release means copying them again |

## Trade-off analysis

A dialect-neutral implementation lets SQLite, which needs no server, exercise every line, so `make check` meets the coverage gate on its own, and the PostgreSQL job exists to prove correctness rather than to reach code. The price is leaving PostgreSQL-only features out of v0.1: `LISTEN/NOTIFY`, advisory locks, `JSONB` and upserts. None of them is needed for correctness. `LISTEN/NOTIFY` is the one with a visible benefit, lower latency for subscribers in other processes, and it can be added later behind the same `subscribe`, with polling kept as the fallback.

Locking the workspace row for the whole transaction serializes commits within a workspace. [ADR-0005](0005-one-event-log-per-workspace.md) already accepted that for `seq`. Holding the lock from the first read, rather than only while assigning `seq`, is what keeps a transaction's loads valid until it saves.

## Consequences

- Easier: one code path to reason about and test, and SQLite is a faithful stand-in for development and tests.
- Easier: applications change their artifact types freely; a change affects validation, not the schema.
- Harder: a subscriber sees commits from another process up to `poll_interval` late, and each caught-up subscription queries the log once per interval.
- Harder: on SQLite every transaction, reads included, holds the database's write lock, so SQLite suits tests, development and single-process applications rather than busy ones.
- Applications that run Alembic's autogenerate on the same database should exclude the `artifactr_` tables (for example with `include_name`), so that they are not proposed for removal.
- Revisit `LISTEN/NOTIFY` if cross-process latency or polling load matters; it is listed in the architecture's open questions.

## Action items

1. [x] Implement `SqlStorage`, `create_sqlite_engine`, `migrate` and `create_schema`, with the initial migration (RFC-0001 phase 4).
2. [x] Run the workspace and storage suites on in-memory storage, SQLite and PostgreSQL, with a PostgreSQL job in CI.
3. [ ] Wake subscribers with PostgreSQL `LISTEN/NOTIFY` if polling latency or load becomes a problem (after v0.1).
