# Multi-tenancy and security

artifactr serves many tenants from one process and one storage. It keeps them apart by construction, and it attributes every change to an actor your application authenticated. Authentication itself is yours. This page describes what the library enforces, what it leaves to you, and where to be careful.

## Tenants and workspaces

A tenant is the top-level isolation boundary: an organization, a customer, or a single user, as your application defines it. Each tenant has any number of workspaces, and each workspace has its own artifacts, threads, proposals and log.

Isolation comes from scoped handles ([ADR-0011](../adr/0011-workspace-scoped-artifacts-and-tenant-handles.md)). `Workspaces.open(tenant_id, workspace_id, actor=...)` is the only place a tenant id enters. The `Workspace` it returns carries its scope, and every storage call it makes is scoped to that tenant and workspace. Nothing below the handle accepts a tenant id, so application code cannot write a query that crosses tenants by mistake. A database-level guard, such as PostgreSQL row-level security, can be layered underneath as defence in depth.

Reading or writing another tenant's data through the public API is a vulnerability; please [report it](../../project/security.md) if you find a way.

## Authentication is the host's

Each surface asks your application who is calling:

| Surface | Hook | Returns |
|---|---|---|
| WebSocket and REST | `resolve_actor(connection)` | The tenant and the actor, or raises `Unauthorized` |
| MCP | `resolve(ctx)` | The tenant and the `ExternalAgentActor` |

The tenant and actor come from these hooks, never from the client's frames or tool arguments, so a client cannot act for another user or reach another tenant by changing its request. That makes the hooks the boundary: verify a session, token or API key there, and derive the tenant from the verified identity rather than from anything the client supplies. Headers, query parameters and names are claims until you have checked them.

The [reference implementation](../reference-implementation.md) trusts an `x-user` header, to stay short. Do not copy that part.

## Authorization

Within a tenant, decide who may do what with an `authorize(tenant_id, workspace_id, actor, access)` hook, which `Workspaces` holds ([ADR-0056](../adr/0056-access-asked-in-every-workspace-method.md)). Every `Workspace` method asks it before it reads or writes anything, with the action it takes (`access.action`, one of `artifactr.workspace.ACTIONS`) and the thread or artifact it names. Every surface reaches storage through those methods, so every REST request, WebSocket command, MCP tool call, resource read and subscription, and in-process call is asked by the same hook; none takes a hook of its own. Over REST, a refusal answers 403; the WebSocket closes with 4403 if it may not open the workspace or read its log, and answers a refused command with a `forbidden` result; MCP fails the tool call, or the read or subscription with `INVALID_PARAMS`, with the same message. Without it, any authenticated actor may do anything in every workspace of its own tenant.

Listing a tenant's workspaces (`Workspaces.list`, `GET /workspaces`, the `list_workspaces` tool) spans the tenant, so it asks `authorize` for `artifactr:read_workspaces` with `workspace_id=None`. It then asks `artifactr:open` in each workspace it finds, and lists only those allowed, so a caller never learns the id of a workspace it can't open ([ADR-0058](../adr/0058-a-tenants-workspaces-listed-by-what-each-actor-may-open.md)). Listing opens nothing, and doesn't call `on_open`.

A subscription, the WebSocket's or an MCP client's, is asked when it opens. Each command on it is asked as it arrives, so a revoked actor's next command is refused, but events keep flowing until the subscription closes.

An agent's run acts for the person whose message or answer started it, `AgentActor.on_behalf_of`, and a turn takes messages from one author only, so one person's message never rides on another's rights ([ADR-0057](../adr/0057-a-turn-acts-for-one-author.md)). An MCP client that carries a person's token should act for them: set `ExternalAgentActor(on_behalf_of=UserActor(...))` in `resolve`. `authorize` can then decide on the person. The runner's own work is asked as `SystemActor(name="runner")`.

Finer rules come from the library itself:

- **Type allowlist.** `Workspaces(storage, types=[...])` rejects creating any artifact type not listed, even one registered elsewhere in the process.
- **Proposals need a second participant.** A proposal must be answered by someone other than its author, so an agent cannot approve its own change, a person cannot approve their own through an agent's run or an MCP client acting for them, and cannot approve in person what their own client proposed.
- **Run facts belong to the agent.** Only a thread's own agent, or the system, may record facts about that thread's runs; clients cannot forge `run_started` or `tool_returned`.
- **Attribution cannot be borrowed.** A handle acts as the actor it was opened for. The agent's handle is derived from yours with `as_actor`, and only your code chooses the actor.

## Keeping agents in bounds

- **Write policies.** Give sensitive types `write_policy = "propose"`, or put a thread in suggest mode, and every agent change waits for a person. This covers external agents over MCP as well as the built-in agent.
- **Approvals.** Declare tools with side effects outside the workspace (publishing, sending email, spending money) with `requires_approval=True`. The run pauses until a person approves or declines the call.
- **Least privilege in your tools.** Application tools run with your application's dependencies (`ctx.deps.app`). Give them only what they need, and check permissions in the tool, not only in the prompt.
- **Artifacts are untrusted input to the model.** Anything a person or another agent writes into an artifact reaches your agent's context, through its instructions, change notes and reads. Treat it like any user message when you decide what the agent's tools may do.

## A NUL character

Text can't hold a NUL character. Every `Workspaces` and `Workspace` method refuses one in an id, a name or a command's text with `validation_failed`, before `authorize` hears it, so a client can't reach PostgreSQL, or your hook, with a string neither can take ([ADR-0061](../adr/0061-a-nul-character-is-refused-at-the-boundary.md)).

## Resource limits
The WebSocket surface closes connections that do not say `hello` within `hello_timeout` (10 seconds), and disconnects clients whose outbox exceeds `outbox_size` frames (1,000) instead of buffering without bound. A disconnected client resumes from the log without losing anything. The library does not limit request sizes, message lengths or command rates; enforce those in your application or at your proxy.

## Reporting vulnerabilities

Report vulnerabilities privately, as described in the [security policy](../../project/security.md).
