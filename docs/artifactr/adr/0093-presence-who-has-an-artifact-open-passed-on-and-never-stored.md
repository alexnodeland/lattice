# ADR-0093: Presence: who has an artifact open, passed on and never stored

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland
**Implements:** [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s live collaboration, parts 1 to 3, artifactr's half: the watch commands, the presence frames and `PresenceChannel`

## Context

- **People draw on a diagram together** (RFC-0006, O5). Each canvas saves its own edits as revisions ([portalr ADR-0074](../../portalr/adr/0074-editing-a-diagram-on-its-canvas-and-the-images-put-on-it.md)). Until now, though, nothing told a canvas who else had the diagram open, where their pointer was, or what they were drawing.
- **The protocol carries durable events and runs' live frames** through one bounded outbox per connection. Overflowing it closes the connection with 4429. Presence is many small frames a second, so it must never fill that outbox.
- **Rights live outside the log.** A grant lost, or an integration switched off, changes nothing in the log a watch could follow.

## Decision

### Frames

These are additive, all in `artifactr.v1`.

- `watch_artifact` and `unwatch_artifact` are commands handled by the transport, as `watch_run` is. They are WebSocket only; over REST they are `invalid_state`.
- A watch is answered with a new outcome, `watching`, which carries the watcher's `rights` on the artifact (`view` or `edit`) and its own `peer`.
  - A watch is checked as a read of the artifact (`Workspace.watch`), so a hidden artifact is `not_found`, exactly as a missing one is.
  - The gate is asked as for an edit that changes nothing, so a watch is `not_enabled` while an integration that governs the artifact is off.
  - It is `edit` if `authorize` allows `artifactr:edit_artifact` on it, else `view`.
- `presence` is a client frame beside `hello` and `command`. It holds:
  - `seq`, increasing per connection;
  - `base_version`;
  - a `pointer`, with finite coordinates;
  - a `selection` of at most 500 ids;
  - `editing`: at most 100 whole elements.
- `peer_presence` is what the others are sent: the same fields, plus `peer`, an opaque id per connection, and `actor`, stamped by the server. A client that names an actor of its own sends no valid frame.
- `peer_left` is sent when a peer unwatches, disconnects, loses its rights, or falls silent. A watcher's own `peer_left`, naming its own `peer`, says that its watch ended, so a client reads no server text to learn it.
- **`hello` may ask for no events** (`events: false`). Such a connection is welcomed and told replay is complete, and is then sent only what it asks for: its commands' results and its watches' presence. A canvas's presence connection asks for none, so it doesn't repeat the workspace's events on a second connection.

### Limits

Each limit is tested.

- A frame is at most 64 KiB, counted as characters of its JSON.
- A connection sends at most 30 presence frames a second across what it watches.
- Past either limit a frame is dropped, with at most one `error` a second.
- A frame for an artifact the connection doesn't watch is dropped silently.
- `editing` from a watch with `view` is dropped, with one `error` per watch.
- **Presence never enters the outbox.** Each connection keeps one frame per peer and artifact, the latest, and its writer sends events first and presence after. A flood of presence never closes a connection with 4429, and the newest frame is the one sent.
- **Rights are read again every 30 seconds** (`artifactr_router(watch_recheck=...)`). Once they are gone, the watcher is sent `peer_left` for everyone it knew there and for itself, and an `error`, and its watch ends. **A read that fails, or doesn't answer within the recheck interval, ends it too:** it fails closed, never watching on unchecked, and logs the error's type alone.
- **One connection watches at most 20 artifacts** (`MOST_WATCHED`), and **one artifact has at most 50 watchers** (`MOST_IN_A_ROOM`, a `LocalPresence` setting): each one's every frame goes to all the others. Past either, `watch_artifact` is `invalid_state`.
- A frame's JSON is made once for every watcher told it, not once each. A restriction in the log ends a watch at the next read too, not at once: within the recheck interval plus the workspace's `hidden_refresh`, about a minute by default.
- **A peer silent for ten seconds is announced as having left** the next time anyone in its room speaks. It stays joined, and is back as soon as it speaks again. A canvas speaks at least every five seconds.

### The port

- **`PresenceChannel`**, in `artifactr.fastapi.presence`, passes presence between the peers in a room, keyed by tenant, workspace and artifact. It has three methods:
  - `join` answers with each other peer's latest frame;
  - `say` tells the others what a peer says;
  - `leave` tells the others the peer left.
- It must deliver each peer's frames in the order the peer said them, since a watcher keeps only the latest it was told.
- **`LocalPresence`**, the default, keeps the rooms in the process. This is enough for one application process, which is stackr's default.
- `artifactr_router(presence=...)` takes another adapter.

## Consequences

- A canvas can show who is there, where their pointer is, and what they are drawing as they draw it (portalr ADR-0078).
- An application that runs several processes shares no presence between them until it has a cross-process adapter. Each process's watchers see only each other.
- Presence is never stored, never bridged, and never seen by a connection that didn't watch.
- **The exposure after access ends.** A person whose grant is lost, or whose integration is switched off, keeps seeing the others' pointers, selections and what they are drawing until the next read of their rights: up to 30 seconds. A restriction in the log is read through the workspace's `hidden_refresh` as well, so up to about a minute by default. A REST read is refused at once, so this is longer. It is what the RFC's cadence chose; a shorter `watch_recheck` narrows it, at the cost of asking `authorize` more often. We keep 30 seconds, and say so here.

## Alternatives considered

- **Presence through the outbox:** rejected. A burst of pointer frames would close the connection that carries the events.
- **A PostgreSQL `LISTEN`/`NOTIFY` adapter now:** deferred, as the RFC's U5 allows. No live frame crosses processes today either (`FanoutChannel` is in-process). The adapter, and the short-lived table its 8,000-byte notification limit calls for, belong with the deployment that runs several processes, and get their own record.
- **A peer removed when silent:** rejected. A watcher that only looks would lose its room and hear nothing more. It is announced as having left, and stays joined.

## Action items

1. [x] The frames, the transport's watches, its limits, and the recheck.
2. [x] `PresenceChannel` and `LocalPresence`.
3. [ ] A cross-process adapter, PostgreSQL's, with its ADR, when a deployment runs several processes.
4. [ ] Agents as peers: a diagram's `Draft` live frames shown as a ghost (RFC-0006, part 4).
