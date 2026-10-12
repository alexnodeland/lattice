# ADR-0015: Cursors, leases and dead letters in the ledger

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Settles two of [RFC-0001](../rfcs/0001-v0.1-implementation-plan.md#unresolved-questions)'s unresolved questions: where a follower's cursor lives, and how it holds its lease.

## Context

A follower reads one artifactr workspace's log in `seq` order and publishes what it selects into the reflexr workspace with the same ids ([stackr RFC-0002][rfc-0002-inbound]). It needs a cursor, so a restarted follower carries on where it was; a lease, so one process at a time follows a workspace; and somewhere to put an envelope it can't bridge. Since RFC-0002, both libraries have grown durable consumer cursors: artifactr's `Workspace.cursor` and `save_cursor` ([artifactr ADR-0046](../../artifactr/adr/0046-telemetry-that-composes-across-libraries.md)) and reflexr's twins. Neither library offers a lease on a workspace to applications: artifactr's `claim_thread` holds a thread, and the leases beneath it are its storage port's, not the `Workspace` API. At startup the bridge must also find every workspace it followed, and neither library can list a tenant's workspaces ([lattice #5][l-5]).

## Decision

- **The ledger holds each followed workspace's cursor and lease, in one row** (`relayr_followers`), and its dead letters (`relayr_dead_letters`). `Ledger.followed()` lists the workspaces with a row, which the followers resume at startup.
- **Exactly once comes from ids, not from the lease.** A bridged event's id is its envelope's, and reflexr's `publish` appends an id once, so two followers, or one that reads an envelope again, publish nothing twice. The lease only keeps a second process from doing the same work.
- **A lease lasts 30 seconds by default, renewed every third of that.** A follower that can't take it tries again every third of that, so a workspace whose follower died is followed again once its lease lapses. A follower whose renewal finds another holder stops relaying, and waits.
- **The cursor moves after the publish.** A follower saves it after each envelope it published or dead-lettered, and after every 500 that bridge nothing, so a restart reads at most that many again. It only moves forward.
- **Dead letters, once per `seq`.** An envelope is dead-lettered, and the follower moves on, when its projection raises (an invalid event included) or reflexr refuses its event as invalid or of a type it doesn't accept (`ValidationFailed`, `NotFound`). Anything else, such as a refused `publish` or a storage failure, stops the follower, which starts again at its cursor the next time the workspace is opened ([ADR-0016](0016-followers-start-on-open.md)).

## Options considered

| Option | For | Against |
|---|---|---|
| **The ledger (chosen)** | Lease, cursor and dead letters in one row and one store; `followed()` lists what to resume | One more table set to migrate |
| artifactr's consumer cursors | No storage of relayr's own for the cursor | The lease and dead letters still need the ledger; nothing lists the workspaces with a cursor; and reading cursors is an action of its own, `artifactr:read_cursors` |
| reflexr's consumer cursors | The cursor beside the published events | The same, and a cursor in the target, not the source |
| A lease through artifactr's storage port | Its leases already exist | Not the `Workspace` API relayr is limited to (ADR-0001), and unchecked by `authorize` |

## Consequences

- Easier: one store answers everything a follower needs, and the followers resume without lattice #5.
- Easier: a follower's guarantees don't rest on its lease, so a lease that lapses under a slow follower costs duplicate work, never a duplicate event.
- Harder: the ledger is one more schema in the application's database, with its own migrations.
- Revisit dead letters when phase 2 adds chain continuation: a continued chain that would pass the depth limit is recorded the same way, by RFC-0002.

[l-5]: https://github.com/alexnodeland/lattice/issues/5
[rfc-0002-inbound]: ../../stackr/rfcs/0002-the-combined-system.md#inbound-artifactr-to-reflexr
