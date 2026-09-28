# ADR-0012: Surfaces: WebSocket thread protocol, REST commands, MCP

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Clients need:

- replay with resume after reconnecting
- several viewers per workspace
- artifacts whose versions the server owns
- live output for runs

External agents (coding assistants, desktop assistants, other services) should be able to join a workspace as participants.

Existing agent-to-UI protocols, AG-UI and the Vercel AI UI message stream, both have adapters in pydantic-ai. Both are scoped to a single HTTP request per run, and in AG-UI the client supplies the state.

## Decision

v1 ships three surfaces. All of them submit through `Workspace.commit` ([ADR-0002](0002-single-write-path.md)) and read through `subscribe` ([ADR-0005](0005-one-event-log-per-workspace.md)):

1. **The WebSocket thread protocol** (`artifactr.fastapi`), specified in [protocol.md](../protocol.md): a hello with `resume_after_seq`, durable event frames, live frames, commands and results.
2. **REST** (`artifactr.fastapi`): the same commands as HTTP endpoints, plus reads.
3. **MCP** (`artifactr.mcp`), on the MCP SDK's `MCPServer`:
   - artifacts are resources
   - commands are tools, attributed to an `external_agent` actor
   - change notifications flow through a `SubscriptionBus` fed by the log
   - it is mounted on the application with `streamable_http_app()`

SSE is deferred. AG-UI and Vercel AI adapters may be added later as compatibility surfaces.

## Options considered

### Option A: Our own thread protocol, plus REST and MCP (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: we own a protocol spec |
| Fit with the model | Exact: resume, several viewers, server-owned versions |
| Ecosystem | No off-the-shelf frontend components |

**Pros:** the protocol expresses the workspace model directly; external agents are first-class.
**Cons:** we maintain the spec and its schema.

### Option B: AG-UI

| Dimension | Assessment |
|---|---|
| Complexity | Low: the adapter exists |
| Fit with the model | Partial: request-scoped runs, client-supplied state |
| Ecosystem | Strong (CopilotKit) |

**Pros:** a standard, with JSON Patch state deltas and interrupts that map to deferred tools.
**Cons:** several viewers, resume and server-owned versions would all be extensions on top.

### Option C: The Vercel AI UI message stream

| Dimension | Assessment |
|---|---|
| Complexity | Low: the adapter exists |
| Fit with the model | Poor: no shared-state concept |
| Ecosystem | Strong for TypeScript (`useChat`) |

**Pros:** drop-in for AI SDK frontends.
**Cons:** request-scoped; artifacts would be out of band.

### Option D: SSE plus POSTed commands

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Fit with the model | Good |
| Ecosystem | Universal |

**Pros:** works through restrictive proxies.
**Cons:** a second streaming transport to maintain in v1.

## Trade-off analysis

The workspace model (a server-owned, versioned, shared log) is the product. Adopting a request-scoped protocol would mean rebuilding that model as extensions to it. The standard protocols remain valuable for simple frontends, and pydantic-ai's adapters make adding them later cheap.

## Consequences

- Easier: every surface behaves identically, because each is an adapter over the same workspace.
- Easier: external agents collaborate under the same rules as people.
- Harder: frontends need a client for our protocol; we provide a JSON Schema to generate types from.
- Revisit SSE and the compatibility adapters after v1.

## Action items

1. [x] Implement the WebSocket endpoint and REST routes in `artifactr.fastapi`.
2. [x] Implement `artifactr.mcp` with resources, tools and a log-fed `SubscriptionBus`.
3. [x] Generate and check in `schemas/artifactr.v1.json`.
