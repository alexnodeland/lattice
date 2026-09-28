# ADR-0022: Surfaces over one command handler

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Building the WebSocket, REST and MCP surfaces (RFC-0001 phase 5) raised decisions [ADR-0012](0012-surfaces-websocket-rest-mcp.md) left to implementation:

- where command handling lives, so the three surfaces cannot drift
- the exact shape of a command frame
- what happens to a client that cannot keep up
- how retried commands are deduplicated
- how MCP resources are named in a multi-tenant server

Testing also surfaced two defects of the drafted protocol:

- `replay_complete` could be withheld indefinitely when the last replayed events belonged to threads the client did not follow.
- A watcher that attached just after a run started could miss the run's first frames, or wait forever if the run had already ended.

## Decision

- **`Runner.execute` is the one command handler.** Messages and answers start, steer or resume runs; `stop_run` stops a run of the caller's workspace that is running in the serving process; every other command is a `Workspace.commit`. The WebSocket session, the REST endpoint and the MCP tools all call it.
- **Command frames nest the command:** `{"type": "command", "command_id": "...", "command": {...}}`. The command is a core `Command`, or the transport-level `stop_run` or `watch_run`. The frame is then a plain discriminated Pydantic model, and the protocol's JSON Schema (`schemas/artifactr.v1.json`) is generated from the models and checked by a test.
- **Slow clients are disconnected, not waited for.** Each WebSocket connection writes through one bounded outbox. On overflow the server closes with 4429; the client reconnects and resumes by `seq`. Events are never dropped from the log to accommodate a connection.
- **Command ids are remembered per process** (bounded, 10,000 by default), keyed by workspace, actor and `command_id`. A retried id returns the original result without running again.
- **`replay_complete` is decided on the unfiltered log**: the session follows every envelope and filters by thread itself, so it always sees the replay reach `head_seq`.
- **Live channels keep each active run's frames** (bounded) and remember recently ended runs. A watcher that attaches mid-run first receives what the run has produced so far, and watching an ended run ends at once.
- **MCP resource URIs include the tenant**: `artifactr://{tenant}/{workspace}/artifacts/{id}`. The notification bus is shared by every tenant, so a URI must not collide across tenants. A client may only read resources of its own tenant. Artifact changes in every workspace a client has used become `ResourceUpdated` notifications.

## Options considered

### Command frame shape

| Option | Typed as one model | Schema generation |
|---|---|---|
| **Nested command (chosen)** | Yes | Direct |
| Flat: command fields next to `command_id` | No: needs a custom parser | Needs schema surgery |

### A client that cannot keep up

| Option | Protects the server | Protects the client's view |
|---|---|---|
| **Disconnect it, and it resumes by `seq` (chosen)** | Yes | Yes: nothing is lost on resume |
| Block the writer | No: memory grows per slow client | Yes |
| Drop events for that client | Yes | No: the client's state silently diverges |

## Consequences

- Easier: adding a surface means authentication plus a translation into `Runner.execute`.
- Easier: frontends generate their types from the checked-in schema.
- Harder: command deduplication and `stop_run` are per process until a shared store or pub/sub channel exists (listed in the architecture's open questions).

## Action items

1. [x] Implement `artifactr.fastapi` and `artifactr.mcp` over `Runner.execute` (RFC-0001 phase 5).
2. [x] Generate `schemas/artifactr.v1.json` and test it for drift.
3. [ ] Share command deduplication and run control across processes (after v0.1).
