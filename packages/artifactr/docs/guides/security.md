# Multi-tenancy and security

artifactr serves many tenants from one process and one storage. It keeps them apart by construction, and it attributes every change to an actor your application authenticated. Authentication itself is yours. This page describes what the library enforces, what it leaves to you, and where to be careful.

## Tenants and workspaces

A tenant is the top-level isolation boundary: an organization, a customer, or a single user, as your application defines it. Each tenant has any number of workspaces, and each workspace has its own artifacts, threads, proposals and log.

Isolation comes from scoped handles ([ADR-0011](../adr/0011-workspace-scoped-artifacts-and-tenant-handles.md)). `Workspaces.open(tenant_id, workspace_id, actor=...)` is the only place a tenant id enters. The `Workspace` it returns carries its scope, and every storage call it makes is scoped to that tenant and workspace. Nothing below the handle accepts a tenant id, so application code cannot write a query that crosses tenants by mistake. A database-level guard, such as PostgreSQL row-level security, can be layered underneath as defence in depth.

Reading or writing another tenant's data through the public API is a vulnerability; please [report it](../project/security.md) if you find a way.

## Authentication is the host's

Each surface asks your application who is calling:

| Surface | Hook | Returns |
|---|---|---|
| WebSocket and REST | `resolve_actor(connection)` | The tenant and the actor, or raises `Unauthorized` |
| MCP | `resolve(ctx)` | The tenant and the `ExternalAgentActor` |

The tenant and actor come from these hooks, never from the client's frames or tool arguments, so a client cannot act for another user or reach another tenant by changing its request. That makes the hooks the boundary: verify a session, token or API key there, and derive the tenant from the verified identity rather than from anything the client supplies. Headers, query parameters and names are claims until you have checked them.

The [reference implementation](../reference-implementation.md) trusts an `x-user` header, to stay short. Do not copy that part.

## Authorization

Within a tenant, decide who may use which workspace with an `authorize(tenant_id, workspace_id, actor)` hook, which the router and `ArtifactrMcp` both take. Over REST, `False` answers 403, and over the WebSocket it closes the connection with 4403. Over MCP, it is asked on every tool call, resource read and resource subscription that names a workspace, and a refusal is a tool error, or a failed read or subscription, with the same message. Without it, any authenticated actor may use every workspace of its own tenant. Pass the same function to both surfaces, so a client cannot reach over one what the other refuses it.

Finer rules come from the library itself:

- **Type allowlist.** `Workspaces(storage, types=[...])` rejects creating any artifact type not listed, even one registered elsewhere in the process.
- **Proposals need a second participant.** A proposal must be answered by someone other than its author, so an agent cannot approve its own change.
- **Run facts belong to the agent.** Only a thread's own agent, or the system, may record facts about that thread's runs; clients cannot forge `run_started` or `tool_returned`.
- **Attribution cannot be borrowed.** A handle acts as the actor it was opened for. The agent's handle is derived from yours with `as_actor`, and only your code chooses the actor.

## Keeping agents in bounds

- **Write policies.** Give sensitive types `write_policy = "propose"`, or put a thread in suggest mode, and every agent change waits for a person. This covers external agents over MCP as well as the built-in agent.
- **Approvals.** Declare tools with side effects outside the workspace (publishing, sending email, spending money) with `requires_approval=True`. The run pauses until a person approves or declines the call.
- **Least privilege in your tools.** Application tools run with your application's dependencies (`ctx.deps.app`). Give them only what they need, and check permissions in the tool, not only in the prompt.
- **Artifacts are untrusted input to the model.** Anything a person or another agent writes into an artifact reaches your agent's context, through its instructions, change notes and reads. Treat it like any user message when you decide what the agent's tools may do.

## Resource limits

The WebSocket surface closes connections that do not say `hello` within `hello_timeout` (10 seconds), and disconnects clients whose outbox exceeds `outbox_size` frames (1,000) instead of buffering without bound. A disconnected client resumes from the log without losing anything. The library does not limit request sizes, message lengths or command rates; enforce those in your application or at your proxy.

## Reporting vulnerabilities

Report vulnerabilities privately, as described in the [security policy](../project/security.md).
