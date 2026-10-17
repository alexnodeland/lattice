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

#### Row-level security

As a second line of defence under artifactr's own scoping, PostgreSQL can keep tenants apart itself ([ADR-0066](../adr/0066-row-level-security-under-the-scoping.md)). The migrations create a policy on each table; it holds for every role but the tables' owner. Create a role that owns nothing, run the migrations as the owner with it, and connect as it with the option on:

```python
owner = create_async_engine("postgresql+asyncpg://owner:secret@localhost/app")
await migrate(owner, application_role="app")  # grants the role artifactr's tables
engine = create_async_engine("postgresql+asyncpg://app:secret@localhost/app")
workspaces = Workspaces(SqlStorage(engine, row_level_security=True))
```

Each transaction then names its tenant in `lattice.tenant_id`, and reads and writes only that tenant's rows; one that names none sees nothing.

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

artifactr's Alembic migrations ship in the package. `migrate(engine)` upgrades the database to the latest schema, creating the tables if they do not exist, and does nothing if it is up to date, so it is safe to run on every start or deploy. Migration 0005 records where each workspace's log stood when it ran, and the runner starts older threads from there ([ADR-0055](../adr/0055-turns-from-the-log.md)). The migrations record their version in their own table, `artifactr_alembic_version`, and every table's name starts with `artifactr_`, so they live beside your application's tables and migrations in the same database without interfering.

If your application runs Alembic's autogenerate on the same database, exclude the `artifactr_` tables from it (with `include_name`, for example), or it will propose dropping them.

`create_schema(engine)` creates the tables directly from the models, without Alembic. It suits tests and prototypes, but a database created this way records no version and cannot be upgraded with `migrate` later.

### How it behaves

- **One writer per workspace at a time.** A transaction creates its workspace's row if the workspace is new, then locks it (`SELECT ... FOR UPDATE`) before loading anything, and `seq` is assigned from that row. On SQLite, the engine's `BEGIN IMMEDIATE` takes the database's write lock instead. Different workspaces commit independently on PostgreSQL.
- **Subscriptions poll.** A subscription reads the log a page at a time. Once it has caught up, a commit made through the same `SqlStorage` wakes it at once, and commits from other processes are seen within `poll_interval` (half a second by default; `SqlStorage(engine, poll_interval=timedelta(seconds=0.2))` to change it). `Workspace.subscribe` reads untraced, so the polls make no traces even with the database instrumented ([Observability](observability.md#polling)).
- **Message ids have a table.** `artifactr_messages` has a row per message id used in a workspace, so checking an id is one key lookup. Migration 0003 fills it from the messages already in the log.
- **Entities are JSON.** Each artifact, proposal, thread and run is stored as its Pydantic model's JSON, beside the columns that reads filter on. Adding a field with a default to your artifact type needs no migration; changing data in ways your model no longer validates does, and that migration is yours.
- **Reads of the log filter in the database.** Each envelope's event type and thread have columns of their own, so a read for some threads selects only what those threads' subscribers receive, and a read of the last so many reads the log backwards from the end.
- **Leases are rows**, taken with a conditional update or an insert, so two processes racing for a thread claim cannot both win.
- **Cursors are rows**, each locked while a save compares it, so the furthest save wins.
- **A cancelled call finishes its statement first.** SQLAlchemy takes a statement cancelled part-way for a lost connection, which on SQLite could keep the database's write lock or the engine's one connection. So every database call is awaited to its end, and a cancellation that came meanwhile is raised after it. A caller cancelled while its statement waits for a lock waits as long as the statement does: on SQLite, the driver's `timeout`; on PostgreSQL, `lock_timeout` if you set one.

The storage does not own the engine: dispose of it when your application shuts down, with `await engine.dispose()`, after closing the `Runner` ([Serving](serving.md#adding-the-router)).

## What a storage guarantees

Every storage method but one takes a `Scope`, a tenant id and a workspace id: the unit of isolation, ordering and locking. The guarantees below are what the rest of the library relies on.

**A tenant's workspaces are listed by id.** `workspaces(tenant_id, after=None, limit=100)` returns a page of the ids of the tenant's workspaces whose logs have an event, ordered as the storage orders strings, after `after`. Reading a workspace, or keeping its cursors or leases, doesn't list it ([ADR-0058](../adr/0058-a-tenants-workspaces-listed-by-what-each-actor-may-open.md)).

**Transactions serialize per workspace from the moment they begin.** `storage.transaction(scope)` returns an async context manager for a `Transaction`. What a transaction loads cannot change before it saves, because no other transaction on that workspace runs meanwhile. Writes are applied atomically when the block exits normally, and an exception rolls back entities, log and history together. This is how `Workspace.commit` runs core's rules, slightly simplified:

```python
async with storage.transaction(scope) as transaction:
    state = State()
    while missing := needs(command, actor=actor, state=state):
        state = merge(state, await transaction.load(missing))
    result = commit(command, state, actor=actor)
    await transaction.save(result, actor=actor, traceparent=current_traceparent())
```

**`seq` is gap-free and assigned at save.** `Transaction.save` stores the result's entities and revisions and appends its events, returning the envelopes with their sequence numbers. The log is a total order per workspace. Each envelope keeps the `traceparent` it was saved with, or `None`.

**`read(scope, after_seq=, before_seq=, threads=, limit=, last=)` reads a window of the log,** the envelopes with `after_seq < seq < before_seq`, oldest first. `threads` keeps what a subscriber following those threads receives, by `artifactr.core.delivered_to`'s rule. `limit` keeps the first so many that match, and `last` the last so many, still oldest first. Filter in the store rather than after reading, so that a tail read of a long log reads only its tail. `Workspace.read` checks the arguments first, so a storage never gets both `limit` and `last`, or a negative number.

**`subscribe(scope, after_seq)` replays, then follows.** One iterator yields the stored envelopes after `after_seq` and then each new one as it commits. Replay for reconnecting clients, MCP notifications, the feedback mirror and a run's watcher follow the log this way; the notes a run starts with are a window `read`.

**A cancelled caller leaves no lock or connection behind.** Cancellation may be deferred until the current statement ends, but a transaction cancelled before it commits rolls back, and the storage is as usable afterwards as before ([ADR-0047](../adr/0047-cancel-safe-storage.md)). Callers are cancelled wherever they are: a stopped run inside a tool's commit, a WebSocket that disconnects mid-replay, a thread claim's renewal, a timeout, or an anyio cancel scope. Three things follow:

- A cancelled call may still have taken effect: a transaction may have committed, or `acquire_lease` taken the lease.
- A wait for a pooled connection cannot be interrupted either, so a task that holds a transaction must not await a task it cancelled.
- The event loop's shutdown is not covered: it cancels the storage's own tasks too, so stop runs with `Runner.aclose` first.

**Leases are exclusive and expire.** `acquire_lease(scope, key, holder, ttl)` takes or renews a lease and returns whether the holder has it; `release_lease` gives it up. `Workspace.claim_thread` uses them to allow one active run per thread, across processes: the claim is renewed while held and lapses by itself if its holder dies. A call that fails or is cancelled as it claims releases the lease, which storage may have granted all the same.

**A lease is read by its key.** `lease(scope, key)` returns the holder and expiry of a lease that hasn't expired, by the storage's clock, or `None`. `Workspace.lease_artifact` uses all three for a lease on an artifact, the key `artifact:<id>`: one holder at a time, renewed only by acquiring it again, and refused to another holder with `ArtifactBusy`, which names the lease. It is advisory, since core doesn't know of it ([ADR-0071](../adr/0071-a-lease-on-an-artifact.md)).

**A claim fences the writes that consume.** `Transaction.holds_lease(key, holder)` says whether the holder still has the lease, expired or not, and keeps it so until the transaction ends: another holder's `acquire_lease` must not take the lease between the answer and the commit. SQL storage locks the lease's row (`SELECT ... FOR UPDATE`), and in-memory storage's `acquire_lease` waits for the workspace's lock. `Workspace.commit` and `Workspace.record` take a `claim=(thread_id, holder)` and refuse with `ThreadBusy`, writing nothing, once another holder has the thread; the runner fences a run's start and a reply's answers that way ([ADR-0069](../adr/0069-a-claim-fences-the-writes-that-consume.md)).

**Cursors only move forward.** `save_cursor(scope, name, seq)` records how far a named consumer of the log has got, and `cursor(scope, name)` reads it back, 0 if it has none. Saving a `seq` below the saved one leaves it, so a consumer that runs in several processes cannot move it back. A `FeedbackMirror` keeps one, so a restarted mirror carries on where it was ([ADR-0046](../adr/0046-telemetry-that-composes-across-libraries.md)); `Workspace.cursor` and `Workspace.save_cursor` give an application's own consumers the same. `Transaction.save_cursor` saves a cursor with a transaction's writes, if it commits; the runner records how far a thread's messages are consumed that way ([ADR-0055](../adr/0055-turns-from-the-log.md)), and `Workspace.commit` and `Workspace.record` take a `cursor=` for it.

**History is opaque bytes.** A thread's model history (pydantic-ai messages, serialized by the agent layer) is appended with `Transaction.append_history`, in the same transaction as the run fact that ends a run segment. Each chunk records the log's head when it was saved, which is how the agent knows what it has already been told.

**Message ids are looked up by key.** `needs` asks for message ids as well as entities; `load` says whether each is used, and `save` records `result.messages` as used ([ADR-0045](../adr/0045-a-message-id-is-used-once.md)).

## Writing your own

Implement the whole `Storage` and `Transaction` protocols from `artifactr.workspace`, `Transaction.holds_lease` and `Storage.lease` among them; the [reference](../reference/workspace.md#storage) lists every method. `InMemoryStorage` is the shortest complete example. Build the envelopes `Transaction.save` returns with `seal`, as both implementations do, so every storage numbers, stamps and scopes them alike. Run the workspace behaviour suite in [`tests/workspace/`](https://github.com/alexnodeland/lattice/tree/main/packages/artifactr/tests/workspace) against your implementation: it states what a storage must do, including rollback, gap-free sequencing, subscriptions that never miss an event, leases, and transactions cancelled at any await.
