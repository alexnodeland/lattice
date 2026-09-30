# ADR-0005: One durable event log per workspace

**Status:** Accepted, amended by [ADR-0021](0021-sql-storage.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Several features need an ordered record of what happened:

- clients replaying history after reconnecting
- the agent's "what changed since I last looked"
- live fan-out to other clients
- in-process hooks
- MCP change notifications

Timestamps are not reliable cursors: clocks skew, and the time an event is created differs from the time it is stored. Separate streams per entity each need their own cursor, and can only be ordered against each other by timestamp. Keeping a durable log, a live broadcast hub and a hook registry as three separate mechanisms creates seams between them, such as events lost between replay and live delivery.

## Decision

- Each workspace has **one append-only log** with a single, gap-free `seq`, assigned inside the commit transaction.
- Every entry is an `Envelope`: the event plus `seq`, `id`, `ts`, `actor`, `workspace_id`, and optional `thread_id` and `run_id`. The stored shape and the wire shape are the same.
- `subscribe(after_seq, where=...)` is the **only read path**, used for replay, live fan-out, hooks, MCP notifications and change notes.
- Core events form a closed discriminated union. Applications extend the log through one open family, `AppEvent`.
- Token-level output is not in the log ([ADR-0007](0007-caller-owned-live-output.md)).

### Amendment (2026-09-29): pages and tails of the log, and joining at its head

`hello` replayed everything after `resume_after_seq`. So a client that needed only what happens next, such as docplan's terminal starting a new thread, first received every workspace-scoped event in the log ([#24](https://github.com/alexnodeland/artifactr/issues/24)). `Workspace.read` read the whole log and filtered threads in Python, so a page of one thread's events cost the whole log, and the tail could only be taken after reading everything. reflexr shares the protocol's shape, and made the same additions with the same names in its ADR-0011.

- **`hello` takes `from_head`.** With `from_head: true`, a connection subscribes from `head_seq`: nothing is replayed, and `replay_complete` follows `welcome` at once. `active_runs` are listed and watched as on any connection.
  - `core.resume` decides this. It refuses `from_head` with a nonzero `resume_after_seq`, and the stream closes with 4400.
  - A client that reconnects resumes from its position, so it cannot skip what it missed by asking for the head again.
  - It is a new optional field, so the protocol stays `artifactr.v1`.
- **`subscribe` stays the only way to follow the log. A read takes a page of it**, and a client follows on from the page's last `seq`. `Storage.read`, `Workspace.read`, `GET /workspaces/{id}/events` and a new MCP tool, `read_events`, take:
  - `after_seq` and a new `before_seq`, for the window `after_seq < seq < before_seq`;
  - `threads`, which REST spells as a repeated `thread_id`;
  - `limit` (the first so many) or a new `last` (the last so many, still oldest first).
- **Using the tail.** `last` reads the tail, and `last` with `before_seq` set to the oldest `seq` a client has pages backwards.
- **Checking arguments.** A read with both `limit` and `last`, or with a negative number, is `validation_failed`. `Workspace.read` checks this once, so storage adapters don't have to.
- **Storage filters threads.** `threads` moved from the handle into the port, because the tail of a filtered log can't be taken after filtering in Python.
  - SQL storage keeps each envelope's event type and thread in new columns, filled from the stored envelopes by migration 0002.
  - It filters with `delivered_to`'s rule: an event with no thread, one whose type is in `core.WORKSPACE_SCOPED`, or one in one of the threads.
  - It reads the last so many backwards from the end.
- **No type filter.** Each library filters its reads the way its `hello` filters: reflexr by event type, artifactr by thread. Everything else has the same names in both.
- **The stream has no tail of its own.** A tail read over REST, followed by `hello` with `resume_after_seq` set to the tail's last `seq`, shows recent history and then everything after it, with no gap. So `hello` needs only a place to start, not a count.

## Options considered

### Option A: One log per workspace (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Ordering | Total order per workspace |
| Throughput | Commits serialize per workspace |

**Pros:** one cursor per client; replay and live delivery are the same call; cross-chat ordering is exact.
**Cons:** a very busy workspace contends on `seq` assignment.

### Option B: Separate streams per thread and per artifact

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Ordering | Per stream only; across streams by timestamp |
| Throughput | No cross-stream contention |

**Pros:** scales writes independently.
**Cons:** several cursors per client; "what changed since" spans streams with no total order.

### Option C: A durable log, a live hub and a hook registry

| Dimension | Assessment |
|---|---|
| Complexity | Medium: three mechanisms |
| Ordering | Log only |
| Throughput | Good |

**Pros:** familiar layering.
**Cons:** replay-then-live needs an explicit barrier; three places to register interest.

## Trade-off analysis

The log carries commits, messages and run lifecycle facts, not tokens, so its write rate is modest even with many concurrent chats. A total order per workspace is exactly what change notes and resume need. Contention can be addressed later by sharding behind the same cursor, if it ever shows up.

## Consequences

- Easier: resume is one number; there is no gap between replay and live delivery.
- Easier: hooks and MCP notifications are just subscribers.
- Harder: `seq` assignment serializes commits within a workspace.
- Revisit retention: once old envelopes are compacted, resume needs a snapshot format.

## Action items

1. [ ] Define `Envelope`, the closed `Event` union and `AppEvent` in core.
2. [ ] Implement `subscribe` for in-memory storage (`asyncio.Condition`) and SQL storage (Postgres `LISTEN/NOTIFY`, polling on SQLite).
3. [ ] Generate the JSON Schema for envelopes into `schemas/`.
