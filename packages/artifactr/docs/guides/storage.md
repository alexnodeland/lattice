# Storage

A workspace keeps its artifacts, revisions, threads, proposals, runs, model history and log in a storage. One protocol, `Storage`, covers all of it, and `Workspaces` takes any implementation ([ADR-0019](../adr/0019-storage-protocol-and-workspace-handles.md)). Application code never calls storage directly: it goes through workspace handles, which hold the tenant and workspace scope.

Two implementations ship:

| Storage | Package | Use it for |
|---|---|---|
| `InMemoryStorage` | `artifactr.workspace` | Tests, examples and single-process prototypes. Nothing survives a restart. |
| `SqlStorage` | `artifactr.sql` (extras) | Everything else: PostgreSQL in production, or SQLite for development and single-process applications |

Both pass the same workspace behaviour suite, so code that works on one works on the other.

## In-memory storage

`InMemoryStorage` keeps everything in the process:

```python
from artifactr import InMemoryStorage, Workspaces

workspaces = Workspaces(InMemoryStorage(), types=[Plan])
```

It implements the whole protocol: transactions that roll back on an exception, a live subscription to the log, leases for thread claims, and history. It keeps nothing across restarts and cannot be shared between processes.

Its clock is injectable, so tests can control when leases expire:

```python
from datetime import UTC, datetime

now = datetime(2026, 1, 1, tzinfo=UTC)
storage = InMemoryStorage(clock=lambda: now)
```

## SQL storage

`SqlStorage` stores workspaces in PostgreSQL or SQLite through SQLAlchemy 2's asyncio extension, with the same code on both ([ADR-0021](../adr/0021-sql-storage.md)). Install the extra for your database; each brings SQLAlchemy, Alembic and the driver:

| Extra | Database | Driver |
|---|---|---|
| `postgres` | PostgreSQL | asyncpg |
| `sqlite` | SQLite | aiosqlite |
| `sql` | Either, with a driver you install yourself | none |

### PostgreSQL

Create an async engine, bring the schema up to date with `migrate`, and give the storage to `Workspaces`:

```python
from sqlalchemy.ext.asyncio import create_async_engine

from artifactr import Workspaces
from artifactr.sql import SqlStorage, migrate

engine = create_async_engine("postgresql+asyncpg://app:secret@localhost/app")
await migrate(engine)  # creates or upgrades artifactr's tables
workspaces = Workspaces(SqlStorage(engine), types=[Plan, Brief])
```

PostgreSQL must run at its default `READ COMMITTED` isolation level.

### SQLite

SQLite has no row locks, so its engine must begin every transaction by taking the database's write lock. `create_sqlite_engine` makes such an engine:

```python
from artifactr.sql import SqlStorage, create_sqlite_engine, migrate

engine = create_sqlite_engine("sqlite+aiosqlite:///app.db")
await migrate(engine)
workspaces = Workspaces(SqlStorage(engine), types=[Plan, Brief])
```

Use a database file. A plain `:memory:` database is a single connection that concurrent transactions would share; for throwaway storage, use `InMemoryStorage` instead. Every transaction, reads included, holds the database's write lock, and waits up to the driver's timeout (5 seconds unless you pass `connect_args`) to get it. That suits tests, development and single-process applications rather than busy ones.

### Migrations

artifactr's Alembic migrations ship in the package. `migrate(engine)` upgrades the database to the latest schema, creating the tables if they do not exist, and does nothing if it is up to date, so it is safe to run on every start or deploy. The migrations record their version in their own table, `artifactr_alembic_version`, and every table's name starts with `artifactr_`, so they live beside your application's tables and migrations in the same database without interfering.

If your application runs Alembic's autogenerate on the same database, exclude the `artifactr_` tables from it (with `include_name`, for example), or it will propose dropping them.

`create_schema(engine)` creates the tables directly from the models, without Alembic. It suits tests and prototypes, but a database created this way records no version and cannot be upgraded with `migrate` later.

### How it behaves

- **One writer per workspace at a time.** A transaction creates its workspace's row if the workspace is new, then locks it (`SELECT ... FOR UPDATE`) before loading anything, and `seq` is assigned from that row. On SQLite, the engine's `BEGIN IMMEDIATE` takes the database's write lock instead. Different workspaces commit independently on PostgreSQL.
- **Subscriptions poll.** A subscription reads the log a page at a time. Once it has caught up, a commit made through the same `SqlStorage` wakes it at once, and commits from other processes are seen within `poll_interval` (half a second by default; `SqlStorage(engine, poll_interval=timedelta(seconds=0.2))` to change it).
- **Entities are JSON.** Each artifact, proposal, thread and run is stored as its Pydantic model's JSON, beside the columns that reads filter on. Adding a field with a default to your artifact type needs no migration; changing data in ways your model no longer validates does, and that migration is yours.
- **Leases are rows**, taken with a conditional update or an insert, so two processes racing for a thread claim cannot both win.

The storage does not own the engine: dispose of it when your application shuts down, with `await engine.dispose()`.

## What a storage guarantees

Every storage method takes a `Scope`, a tenant id and a workspace id: the unit of isolation, ordering and locking. The guarantees below are what the rest of the library relies on.

**Transactions serialize per workspace from the moment they begin.** `storage.transaction(scope)` returns an async context manager for a `Transaction`. What a transaction loads cannot change before it saves, because no other transaction on that workspace runs meanwhile. Writes are applied atomically when the block exits normally, and an exception rolls back entities, log and history together. This is how `Workspace.commit` runs core's rules, slightly simplified:

```python
async with storage.transaction(scope) as transaction:
    state = State()
    while missing := needs(command, actor=actor, state=state):
        state = merge(state, await transaction.load(missing))
    result = commit(command, state, actor=actor)
    await transaction.save(result, actor=actor)  # assigns seq, appends events
```

**`seq` is gap-free and assigned at save.** `Transaction.save` stores the result's entities and revisions and appends its events, returning the envelopes with their sequence numbers. The log is a total order per workspace.

**`subscribe(scope, after_seq)` replays, then follows.** One iterator yields the stored envelopes after `after_seq` and then each new one as it commits. Replay for reconnecting clients, live fan-out, MCP notifications and the agent's change notes all read the log this way.

**Leases are exclusive and expire.** `acquire_lease(scope, key, holder, ttl)` takes or renews a lease and returns whether the holder has it; `release_lease` gives it up. `Workspace.claim_thread` uses them to allow one active run per thread, across processes: the claim is renewed while held and lapses by itself if its holder dies.

**History is opaque bytes.** A thread's model history (pydantic-ai messages, serialized by the agent layer) is appended with `Transaction.append_history`, in the same transaction as the run fact that ends a run segment. Each chunk records the log's head when it was saved, which is how the agent knows what it has already been told.

## Writing your own

Implement the `Storage` and `Transaction` protocols from `artifactr.workspace`; the [reference](../reference/workspace.md#storage) lists every method. `InMemoryStorage` is the shortest complete example. Run the workspace behaviour suite in [`tests/workspace/`](https://github.com/alexnodeland/artifactr/tree/main/tests/workspace) against your implementation: it states what a storage must do, including rollback, gap-free sequencing, subscriptions that never miss an event, and leases.
