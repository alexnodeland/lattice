# ADR-0047: Cancel-safe storage

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

Storage calls are cancelled from many places:

- `Runner.stop`, which can land inside a tool's commit or the capability's `record`
- a WebSocket that disconnects, whose tasks are cancelled, mid-replay among others
- the capability's run watcher, and a thread claim's renewal inside `acquire_lease`, cancelled as their run or claim ends
- the MCP SDK's anyio cancel scopes, which cancel their task again until it ends
- `ArtifactrMcp.aclose`, and a feedback mirror stopped with its application

SQLAlchemy takes a statement cancelled part-way for a lost connection. A SQLite engine keeps one pooled connection and takes the database's write lock with `BEGIN IMMEDIATE`, so a cancelled statement could drop the connection still holding the lock, or never return it to the pool, and lock the process out of its own database. PostgreSQL loses the connection too. Cancelling a commit, a read, a lease and a subscription's page 100 times each, in three ways, broke 9 or 10 of the 12 cases on SQLite and 6 of the 12 on PostgreSQL.

reflexr makes the same decision, with the same helper ([reflexr ADR-0042](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0042-cancel-safe-storage.md)).

## Decision

- **Cancel-safety is part of the `Storage` port's contract.** A cancelled caller leaves no lock or connection behind; cancellation may be deferred until the current statement ends. A transaction cancelled before it commits rolls back. The protocol says so, and the behaviour suite checks every storage by cancelling a transaction after each number of yields in turn.
- **`InMemoryStorage` keeps it as it is.** A transaction stages its writes and holds an `asyncio.Lock`; a cancellation drops the writes and releases the lock.
- **`SqlStorage` awaits every database call to its end.** `_to_the_end(call)` runs the call in a task of its own and waits for it, catching every cancellation that comes meanwhile and raising it once the call has ended. It wraps each `_Transaction` method, through a decorator; the transaction's lock, commit and close; and the reads, leases and cursors outside transactions. Closing the session rolls back whatever it did not commit, and returns its connection to the pool.
- **`Runner.aclose()` stops the process's runs, waits for them, and starts no more,** so an application stops its runs before the event loop ends and its storage closes.

## Options considered

| Option | Covers | Cost |
|---|---|---|
| **In each storage adapter, as a contract of the port (chosen)** | Every canceller | One helper and a decorator in `artifactr.sql`; each adapter keeps the contract |
| `asyncio.shield` around each call | Every canceller | A shielded call outlives its cancelled task, so the task's next statement can race it |
| Callers never cancel mid-call | Nothing it can enforce | anyio's cancel scopes, `Runner.stop` and a server's cancelled tasks cancel a task wherever it is |

## Consequences

- Easier: anything can cancel anything, on every storage, and `Runner.stop` cancels a run wherever it is.
- Harder: a cancellation waits for the statement in flight, and one waiting for a lock waits as long as the database lets it: on SQLite, the driver's `timeout`; on PostgreSQL, `lock_timeout` if the application sets one.
- Harder: a cancelled call may still have taken effect. A transaction may have committed, or `acquire_lease` taken the lease, before the cancellation is raised.
- Harder: a wait for the pool's connection cannot be interrupted either. A task that holds a transaction must not await a task it cancelled, which may be waiting for that transaction's connection.
- Harder: an anyio cancel scope cancels its task again at every turn of the loop until the task ends, so the caller spins the loop for the whole statement. On Linux that starves aiosqlite's thread of the GIL, and the statement takes far longer to end.
- Harder: the event loop's shutdown is not covered. `asyncio.run` cancels every task left, `_to_the_end`'s own task too, so the statement is cut off after all. Stop runs with `Runner.aclose()` before the loop ends.
- Harder: a storage adapter must keep the contract. The behaviour suite's cancellation case checks it.

## Action items

1. [x] Cancel-safe `SqlStorage`, the contract on `Storage`, and `Runner.aclose`.
