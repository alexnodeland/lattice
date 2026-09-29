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

## Amendment (2026-09-29): the runner remembers commands' results, for every surface

The router remembered command results itself, so REST and the WebSocket answered a retried `command_id` with its first result, and MCP, whose tools took no id, could not: an agent that retried `post_message` posted twice ([#49](https://github.com/alexnodeland/artifactr/issues/49)).

- **`Runner.execute_once(workspace, command, command_id=...)`** carries out a command the first time its id is seen and remembers its result, outcome or rejection, as a `command_result`. A repeated id returns the remembered result and carries nothing out, whatever command it comes with. REST, the WebSocket and MCP all call it, so one memory serves them all.
- **The memory is a port**, `CommandResults` (`get` and `put`), owned by `artifactr.agent` beside the runner ([ADR-0034](0034-ports-and-adapters-for-integrations.md)). `InMemoryCommandResults`, the default, keeps the 10,000 most recent results in the process and forgets the oldest first, as the router did. An adapter over shared storage would deduplicate across processes; none exists yet. `artifactr_router` no longer takes `remembered_commands`: the capacity is the adapter's.
- **The key is the tenant, the workspace, the sender's participant and the `command_id`.** The tenant is new, since two tenants may give a workspace the same id. The participant replaces the actor's full value, so a person whose display name changed between a request and its retry is still recognised.
- **MCP tools that change something take an optional `command_id`.** The MCP request id cannot serve: a retried call is a new request, with a new id.
- **A recorded message or answer names its run.** The `recorded` outcome gains `run_id`: the run a `post_message` or `answer_deferred` started or resumed, or `null`. A retried `post_message` then reports the run the first one started, and any client learns its run from the command's result, then reads it with `GET .../runs/{run_id}` or MCP's `get_run`. This is an additive change to v1.
- **No list of runs.** REST gains none, and neither does MCP. A client that started a run has its id from the result, the WebSocket's `welcome` lists the active runs, and the log holds every run's events. reflexr lists runs, since its rules start them without a client; here a person or client always does.

A retry that arrives while its first attempt is still being carried out is not deduplicated: both miss the memory and both run, as before. A shared adapter would need to claim a command while it runs; the architecture lists this among its open questions.

## Action items

1. [x] Implement `artifactr.fastapi` and `artifactr.mcp` over `Runner.execute` (RFC-0001 phase 5).
2. [x] Generate `schemas/artifactr.v1.json` and test it for drift.
3. [ ] Share command deduplication and run control across processes (after v0.1).
