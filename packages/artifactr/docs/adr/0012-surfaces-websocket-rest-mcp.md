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

## Amendment (2026-09-29): every surface takes the authorize hook

The router took an `authorize(tenant_id, workspace_id, actor)` hook, but `ArtifactrMcp` did not, so an authenticated MCP client could use every workspace of its tenant however the application restricted REST and the WebSocket.

- **`ArtifactrMcp(authorize=...)`** takes the router's hook and asks it on every tool call, resource read and resource subscription that names a workspace, before the workspace is opened or followed. A refusal is a tool error, or a failed resource read or subscription, carrying the message of the router's 403, "this workspace is not yours to use". Listing the tools and the resource template names no workspace, and is not asked. Without the hook, every workspace of the client's tenant is allowed, as before.
- **A subscription is checked when it opens.** The MCP SDK serves `subscriptions/listen` itself, so a middleware on the server makes a resource read's checks for each artifact a stream names: that the artifact is the client's tenant's, and `authorize`. Until now a client could listen for changes to any tenant's artifacts, learning which changed and when. The check is made once per stream, as the WebSocket's is made once per connection. The SDK calls its middleware provisional; its version is pinned in `uv.lock`, and the tests exercise the check through the SDK's client.
- **The hook's type, `Authorize`, lives in `artifactr.workspace`,** beside `Workspaces.open`, since an adapter may not import another ([ADR-0034](0034-ports-and-adapters-for-integrations.md)). `artifactr.fastapi.Authorize` is the same alias, re-exported.

reflexr made the same change for its tools and resource reads in its ADR-0011.

## Action items

1. [x] Implement the WebSocket endpoint and REST routes in `artifactr.fastapi`.
2. [x] Implement `artifactr.mcp` with resources, tools and a log-fed `SubscriptionBus`.
3. [x] Generate and check in `schemas/artifactr.v1.json`.
