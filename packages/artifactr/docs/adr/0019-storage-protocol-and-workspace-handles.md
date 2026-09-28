# ADR-0019: One storage protocol behind workspace handles

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Implementing the workspace layer (RFC-0001 phase 2) required settling what [ADR-0011](0011-workspace-scoped-artifacts-and-tenant-handles.md) and [ADR-0018](0018-core-host-contract.md) left open:

- How many interfaces a storage backend implements, and what they must guarantee.
- How the "one active run per thread" rule holds across processes and survives crashes.
- Where the agent's model history is stored, given that the workspace layer must not depend on pydantic-ai.
- How an application stops clients from creating artifact types it does not use, since every registered type is creatable by default.

## Decision

- **One `Storage` protocol**, with a `Transaction` for writes. Every method takes a `Scope` (tenant and workspace); `Workspace` handles hold the scope, so application code never passes it.
- **Transactions serialize per workspace from the moment they begin**, so what a transaction loads cannot change before it saves. In memory this is a per-workspace lock; in SQL it will be a lock on the workspace row. Writes are staged and applied atomically when the block exits normally; an exception rolls everything back, including the log.
- **`subscribe(after_seq)` replays then follows live** on one iterator, so there is no gap between history and live events. Thread filtering (`delivered_to`) is a pure core rule applied by the workspace.
- **Thread claims are storage leases** (`acquire_lease`, `release_lease`) with a time-to-live that `Workspace.claim_thread` renews while held. A claim holds across processes and lapses on its own if its holder dies.
- **Model history is opaque bytes**, appended per run segment in the same transaction as the run fact that ends the segment (`Workspace.record(fact, history=...)`). The agent layer serializes with pydantic-ai's `ModelMessagesTypeAdapter`; the workspace never imports pydantic-ai.
- **`Workspaces(storage, types=[...])` is an allowlist.** Creating (or proposing to create) a type outside it is rejected as `not_found`, whatever is registered.

## Options considered

### Storage interface

| Option | Implementer burden | Consistency |
|---|---|---|
| **One protocol (chosen)** | One class to write | One transaction covers state, log and history |
| Separate artifact, log, history and lease stores | Several classes | Cross-store atomicity is the implementer's problem |

### Enforcing one run per thread

| Option | Survives crashes | Works across processes |
|---|---|---|
| **Leases with a time-to-live (chosen)** | Yes: they expire | Yes |
| An `active_run` field on the thread, set and cleared by core | No: a crash leaves it set forever | Yes |
| An in-process lock | Yes | No |

## Consequences

- Easier: a new backend implements one protocol, checked by the same behaviour suite the built-in backends run.
- Easier: history, run state and the log can never disagree after a crash, because they commit together.
- Harder: every commit to a workspace waits for the one before it. This is the same trade-off [ADR-0005](0005-one-event-log-per-workspace.md) accepted for `seq`.

## Action items

1. [x] Implement `Storage`, `Workspaces`, `Workspace` and `InMemoryStorage` (RFC-0001 phase 2).
2. [ ] Implement `SqlStorage` against the same behaviour suite (phase 4).
