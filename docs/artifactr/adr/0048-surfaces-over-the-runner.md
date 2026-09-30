# ADR-0048: Surfaces over the runner

**Status:** Accepted; the run a recorded message names amended by [ADR-0055](0055-turns-from-the-log.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

Clients need replay with resume after reconnecting, several viewers per workspace, artifacts whose versions the server owns, and live output for runs. External agents (coding assistants, desktop assistants, other services) should join a workspace as participants.

[ADR-0012](0012-surfaces-websocket-rest-mcp.md) decided the surfaces, and [ADR-0022](0022-surfaces-over-one-command-handler.md) the command handler they share. Their amendments changed both: every surface takes the `authorize` hook, MCP reads what REST reads, the runner remembers commands' results, and a recorded message names its run. That left two public entry points, `Runner.execute`, which raised rejections, and `Runner.execute_once`, which returned a `command_result`; MCP called one or the other, and the router handed the WebSocket its REST handler, whose `watch_run` guard the stream never reached, since it handles `watch_run` itself. This record states the decision as it stands, superseding both.

## Decision

- **Three surfaces, each a thin adapter over the runner and a `Workspace` handle:**
  - **The WebSocket thread protocol** (`artifactr.fastapi`), specified in [protocol.md](../protocol.md): `hello` with `resume_after_seq` or `from_head`, durable event frames, live frames, commands and results.
  - **REST** (`artifactr.fastapi`): the same command frames at `POST .../commands`, and reads of artifacts, revisions, the log, threads, proposals and runs.
  - **MCP** (`artifactr.mcp`), on the MCP SDK's `MCPServer`: artifacts are resources at `artifactr://{tenant}/{workspace}/artifacts/{id}`, commands and REST's reads are tools, and artifact changes become resource-updated notifications on a `SubscriptionBus` fed by the log.
- **One command handler: `Runner.execute(workspace, command, *, command_id) -> CommandResult`.** Messages and answers start, steer or resume runs; `stop_run` stops a run of the workspace that runs in the serving process; every other command is a `Workspace.commit`. A rejection is the result, never raised. The WebSocket and REST pass the frame's `command_id`, and MCP the tool's, or a new one. `watch_run` is the WebSocket's own; REST refuses it as `invalid_state`.
- **A command is carried out once per id.** The runner remembers each result in a `CommandResults` port, keyed by the tenant, the workspace, the sender's `participant` and the `command_id`, so a retry returns the first result on every surface. `InMemoryCommandResults`, the default, keeps the 10,000 most recent in the process. Beyond that memory, core refuses a create or a message whose id is already used ([ADR-0045](0045-a-message-id-is-used-once.md)).
- **A recorded message or answer names its run.** `Recorded.run_id` is the run a `post_message` or `answer_deferred` started or resumed, or `null`. Only the runner knows it, so the runner sets it, and core never does. It stays on core's outcome because it is on the wire.
- **Authentication is the host's.** The router takes `resolve_actor(connection)` for REST and the WebSocket, and `ArtifactrMcp` takes `resolve(ctx)`, whose `ctx` is an `McpContext`.
- **Authorization within a tenant is one hook, asked in one place.** The router and `ArtifactrMcp` take the same `authorize(tenant_id, workspace_id, actor)` (`artifactr.workspace.Authorize`) and pass it to `Workspaces.open(..., authorize=)`, which raises `Forbidden` ("this workspace is not yours to use") before the handle exists. REST answers 403 with the rejection's payload, as every REST error; the WebSocket closes with 4403; MCP fails the tool call, and a resource read or subscription with `INVALID_PARAMS` carrying the rejection. The MCP SDK serves `subscriptions/listen` itself, so a middleware checks each artifact a subscription names, once, when it opens.
- **What a surface reads, the workspace answers.** `Workspace.artifacts(kind=)` filters in storage, and `Workspace.revisions` raises `NotFound` for an artifact that does not exist, so no surface checks either itself.
- **Command frames nest the command:** `{"type": "command", "command_id": "...", "command": {...}}`, a plain discriminated Pydantic model, from which `schemas/artifactr.v1.json` is generated and checked.
- **Slow clients are disconnected, not waited for.** Each connection writes through one bounded outbox; on overflow the server closes with 4429, and the client resumes by `seq`.
- **`replay_complete` is decided on the unfiltered log,** so it always comes, whichever threads the client follows. Live channels keep each active run's frames, so a watcher that attaches mid-run first receives what the run has produced so far.
- **Deliberate differences:** MCP's `read_events` returns the first 50 envelopes when given no `limit` or `last`, for a model's context, where REST returns every one; `watch_run` and live frames are the WebSocket's.

## Options considered

The protocol:

| Option | Fit with the model | Ecosystem |
|---|---|---|
| **Our own thread protocol, plus REST and MCP (chosen)** | Exact: resume, several viewers, server-owned versions | No off-the-shelf frontend components |
| AG-UI | Partial: request-scoped runs, client-supplied state | Strong (CopilotKit) |
| The Vercel AI UI message stream | Poor: no shared state | Strong for TypeScript (`useChat`) |
| SSE plus POSTed commands | Good | Universal, but a second streaming transport |

The command handler:

| Option | Assessment |
|---|---|
| **One public `execute` that returns a `command_result` (chosen)** | Every surface calls the same method the same way, and deduplication cannot be skipped |
| `execute`, which raises, beside `execute_once`, which returns a result | Two entry points, and a surface that forgets the id skips the memory |

A client that cannot keep up:

| Option | Protects the server | Protects the client's view |
|---|---|---|
| **Disconnect it, and it resumes by `seq` (chosen)** | Yes | Yes: nothing is lost on resume |
| Block the writer | No: memory grows per slow client | Yes |
| Drop events for that client | Yes | No: its state silently diverges |

## Consequences

- Easier: a new surface is authentication plus a translation into `Runner.execute`.
- Easier: every surface behaves identically, refuses a workspace alike, and answers a retry with its first result.
- Easier: frontends generate their types from the checked-in schema.
- Harder: frontends need a client for our protocol.
- Harder: deduplication and `stop_run` are per process until a shared store or channel exists (listed in the architecture's open questions).
- Revisit SSE and the AG-UI and Vercel AI compatibility adapters, which pydantic-ai makes cheap, when a simple frontend needs them.

## Action items

1. [x] The WebSocket, REST and MCP surfaces over `Runner.execute`.
2. [x] `authorize` on every surface, through `Workspaces.open`.
3. [ ] Share command deduplication and run control across processes.
