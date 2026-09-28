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
