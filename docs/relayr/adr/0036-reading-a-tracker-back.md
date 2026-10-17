# ADR-0036: Reading a tracker back

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Builds phase 2 of [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md): its [Reading back](../../rfcs/0004-relayr-and-task-trackers.md#reading-back), [Echoes and loops](../../rfcs/0004-relayr-and-task-trackers.md#echoes-and-loops), [Nudges](../../rfcs/0004-relayr-and-task-trackers.md#nudges) and [Budget](../../rfcs/0004-relayr-and-task-trackers.md#budget). It follows the RFC's recommendations T1 (snapshots diffed by relayr), T2 (one `tracker:` namespace) and T7 (echoes dropped by value, people's changes joining chains without depth, and a cap of 20 writes per item an hour), which the RFC leaves to the maintainer's sign-off. It amends [ADR-0006](0006-bridged-types-in-the-artifactr-namespace.md) and [ADR-0018](0018-bridged-events-their-fields-ids-and-projections.md), with a second namespace of relayr's types and its projections. Where the code departs from the RFC's text, this says so, and why.

## Context

Phase 1 ([ADR-0033](0033-the-tracker-port-and-runs-that-write-to-it-once.md)) lets runs file and change items, once. Nothing came back: a person closing an item a run filed was invisible to rules. Neither tracker sends a stable event id, Plane deactivates a webhook after five failed deliveries, and Vikunja keeps its delivery queue in memory, so the RFC trusts only what relayr can read back. Plane v1.4.2 sends no webhook at all when a work item or a comment is deleted ([ADR-0035](0035-what-phase-1-settled-of-the-trackers-unknowns.md), confirmed live in [ADR-0037](0037-what-a-live-plane-settled.md)).

## Decision

- **A follower per bound workspace,** `TrackerFollowers`, holds the workspace's tracker lease in the ledger (30 s, renewed every third of that) and polls its project every 30 s. Each poll reads what changed since two minutes before its cursor, compares each item with its snapshot in the ledger, and publishes one event per field that differs and one per new comment. It saves the snapshots, then its cursor, `(updated_at, id)`, which only moves forward. `watch` is the `on_open` hook, and `resume` follows every bound workspace at startup.
- **Ids are derived:** `trk_` and 16 hex digits of a SHA-256, joined by NUL bytes, over the tenant, the workspace, the project and the tracker, then what the event says: for a change, the item's id, the field, a digest of the new value as canonical JSON, and the item's `updated_at`; for a creation or a removal, the item's id, `created` or `removed`, and its `updated_at`; for a comment, `comment` and the comment's id. reflexr appends an id once, so a page read again, by another replica or after a restart, publishes nothing new. An item whose snapshot row is lost reads as new, once; nothing already published is published again.
- **A new binding is seeded silently:** its first read snapshots every item and publishes nothing, unless the binding names a `since`, from which items changed are published as created. A seeded item's comments until its last change are old.
- **A sweep reads the whole project** once a day, and on the first read: an item no longer listed is `tracker:item_removed`. For an item lattice filed, its key's lookup tells deleted from archived, and a deleted one's key is marked, so it files nothing again. Plane sends no delete webhook, so the sweep is the only way a deletion is found on either tracker.
- **The four types** are `tracker:item_created`, `tracker:item_changed` (`field`, `old`, `new`, `actor`), `tracker:item_commented` and `tracker:item_removed` (`deleted` when known), under `TrackerEvent(Event, abstract=True, event_namespace="tracker")` in `relayr.trackers.events`. Every event carries the tracker, the project, and the item's id, number, name, link and key. `TRACKED` lists them for reflexr's `events=`, and `PUBLISHERS` reserves the namespace to `SourceActor(name="tracker")` for its `publishers=` (reflexr ADR-0057).
- **Projections are per bound workspace:** a function from the `tracker:` event to the application's own, or None. An exception, or one of reflexr's own events, dead-letters the event in `relayr_tracker_dead_letters`, once per event id. Anything else stops the follower until its workspace is opened again, as the artifactr followers do.
- **relayr's own writes are dropped by value.** Filing records the values it files, as the tracker will hold them, before it creates the item; an edit records its values before it sends them, as phase 1 did. A field read back holding the value recorded for it is an echo: it isn't published, and the recorded value is consumed, so a person who later sets that value again is published. The first read of a binding consumes them too. An item whose key lattice claimed isn't published as created, and a comment lattice posted, which the adapter reads with its key, isn't published at all.
- **A person's change on an item a run filed joins that run's chain,** by the correlation id on the key's row, without causation, so depth never grows through a tracker. If reflexr no longer has that chain, the event starts its own.
- **The cap on loops** is 20 writes by relayr to one item an hour, counted in the ledger by the tracker's id for the item, so it holds across replicas. The next write fails its run for good, as `tracker_loop`, and is counted.
- **Webhooks only nudge.** `relayr.fastapi.tracker_router(followers)` mounts `POST /relayr/v1/trackers/{tenant}/{tracker}`. A body over 1 MB is refused once it says so, or once that much is read; a signature is checked first, with the credentials the tenant's followers last asked for, never asked for on a request, and only then is the integration's switch asked; an unknown tenant, a switched-off workspace and a bad signature are the same 401, counted together. A verified nudge wakes the followers this process runs of the project it names, debounced by 2 s, and answers 204.
- **The budget** is per tenant's key and per process, 40 requests a minute by default (`Trackers(budget=...)`): runs' writes spend it and are never held back, and polls take only what is left. A poll that finds nothing left waits for its next interval; a poll whose comments run out of budget stops at that item, and its cursor moves only past what it read. A 429 makes a follower wait out `Retry-After`, with up to a second of jitter.
- **Switched off is nothing.** Each poll, nudge and wait asks the workspace's `Enabled` first: a follower switched off reads nothing, writes nothing, and lets its lease go until it is switched on.
- **Counted:** `relayr.trackers.unnudged` (changes a poll published that no nudge announced, but removals, which no webhook announces), `relayr.trackers.nudges_refused`, `relayr.trackers.dead_letters` and `relayr.trackers.loops`; a stopped follower counts in `relayr.followers.stopped`.

### Where it departs from the RFC

- **Snapshots have a table of their own,** `relayr_tracker_snapshots`, keyed by the tracker's id for the item: four tables in all where the RFC has three. The RFC's item table grows with every item in a bound project, keyed by item; phase 1's `relayr_tracker_items` is keyed by lattice's key, for claims, and an item a person filed has none. Its rows also keep relayr's recent writes to the item, which the cap counts. The two new tables the RFC names, `relayr_tracker_followers` and `relayr_tracker_dead_letters`, are as it has them.
- **No `Ledger.tracker_followed()`.** Bindings are configuration, given to `Trackers`, so `resume` follows every binding it was given, whether or not its workspace was ever opened. Nothing reads across tenants, and [ADR-0027](0027-row-level-security-under-the-scoping.md)'s one read across tenants stays the only one.
- **The port gains `holds(state)`,** the state an item set to a state reads back as: Plane holds all five, Vikunja's `done` flag two. Filing and edits record what the tracker will hold, so the echo filter compares like with like; and `update` no longer sends `started` to a Vikunja task that is already `todo`, which ADR-0033 noted it did. An adapter an application wrote must add it, as the ledger's methods.
- **`tracker_router(followers)`,** not `tracker_router(trackers)`: what it wakes are the followers, and they hold the connector.
- **Recorded values are consumed** when the follower reads them back. The RFC drops an echo by value, and says nothing about the value after; kept, it would drop a person's later change to it for good.
- **`actor`** is the item's last updater only when nothing relayr wrote is among the changes read: an item shows only its last updater, and on Plane that is "who last patched it", which a comment doesn't move (ADR-0037).
- **`since` publishes the items changed since** as created, where the RFC says items "are published as created" from it: neither tracker's port item has a creation time.
- **`update` still changes only items lattice filed,** which ADR-0033 left for phase 2. A person's item has a snapshot now, but recording relayr's values on it needs them keyed by item, not by lattice's key, and no rule needs it yet.

## Options considered

| Option | For | Against |
|---|---|---|
| **Snapshots in a table of their own (chosen)** | One row per item, by the tracker's id; claims stay as phase 1 made them | A fourth table |
| Snapshots in `relayr_tracker_items`, as a third kind | Three tables, as the RFC has | Rows whose claim columns mean nothing, keyed by something else |
| The write cap in each process's memory | No table | Replicas multiply it, and a restart resets it |
| Resume from the ledger (`tracker_followed`) | Bindings could change at run time | A second read across tenants, for bindings that are configuration |

## Consequences

- A rule reacts to what people do in the tracker as it reacts to what they do in a chat, once per change, in the chain of the run that filed the item.
- Changes are level-triggered: two between polls are one, and one undone between polls is none. A comment posted in the same second as an item's last change on Vikunja, which keeps time to the second, waits for the item's next change.
- An echo can be missed when relayr writes one field twice between polls and a poll reads between them: the first value is no longer recorded, so it is published as a person's. The cap ends any loop it starts.
- A poll is not renewed while it runs: one longer than the lease lets another replica start, and the derived ids keep what both publish to once.
- An archived item lattice filed, unarchived later, publishes nothing: its key's claim reads as relayr's creation. An item the sweep removes forgets its writes, and so its count under the cap.
- A process that dies after saving a poll's snapshots and before consuming its echoes leaves those values recorded, so a person who sets one of them later is dropped once, as is a value relayr recorded before phase 2 that no read ever matched. The other order would publish relayr's own writes.
- A ledger an application wrote must add eleven methods; relayr's pass the contract test on memory, SQLite and PostgreSQL, with and without row-level security.
