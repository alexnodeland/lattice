# ADR-0007: Live output is owned by the caller, not the log

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr must be multi-tenant and support many concurrent chats. Token-level output (text deltas, tool-call argument deltas, drafts) is high-volume and only useful while it is happening. Routing it through the durable log, or the log's pub/sub, would make storage the bottleneck and the blast radius for every chat of every tenant.

pydantic-ai already hands a run's event stream to whoever drives the run, through `event_stream_handler` or `run_stream_events`.

## Decision

- The durable log carries **domain events only** ([ADR-0005](0005-one-event-log-per-workspace.md)).
- The caller of `agent.run` supplies a **`LiveChannel`** as an independent parameter: `event_stream_handler=forward_live(channel)`.
- `forward_live` maps pydantic-ai stream events and application `CustomEvent`s to the protocol's live frames.
- Channel implementations:
  - `WebSocketChannel`, for the connection that started the run
  - `FanoutChannel`, in-process and keyed by `run_id`, for other watchers
  - an optional Redis or NATS channel, for fan-out across replicas
  - `NullChannel`, for headless runs
- Live frames are best-effort. Durable events (`assistant_message`, `tool_returned`, `artifact_changed`) are authoritative.
- Runs hold a lease, not a socket: if the starting connection drops, the run continues and the channel detaches.

## Options considered

### Option A: A caller-owned channel (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Multi-tenant scale | High: live traffic never touches storage |
| Multiple viewers | Via a fan-out channel |

**Pros:** live output scales independently of the log; uses pydantic-ai's own seam.
**Cons:** watching another client's run needs a fan-out channel.

### Option B: Everything through the log

| Dimension | Assessment |
|---|---|
| Complexity | Low for clients |
| Multi-tenant scale | Poor: every token passes through storage and pub/sub |
| Multiple viewers | Built in |

**Pros:** one stream for everything.
**Cons:** the log becomes a token bus.

### Option C: The caller drives the stream, with no fan-out

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Multi-tenant scale | High |
| Multiple viewers | None |

**Pros:** simplest.
**Cons:** other clients see output only after it is durable.

## Trade-off analysis

Option A keeps Option C's scaling properties and adds fan-out as an opt-in channel implementation, without making the log carry traffic it does not need to keep.

## Consequences

- Easier: live traffic is isolated per run and can be scaled or dropped freely.
- Easier: headless and scheduled runs need no special casing.
- Harder: reconnect means two steps: replay durable events by `seq`, then reattach to the run's live channel.
- Revisit if clients need guaranteed delivery of intermediate output.

## Action items

1. [ ] Define the `LiveChannel` protocol and `forward_live`.
2. [ ] Implement `WebSocketChannel`, `FanoutChannel` and `NullChannel`.
3. [ ] Specify live frames in [protocol.md](../protocol.md).
