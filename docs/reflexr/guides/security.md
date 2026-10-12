# Multi-tenancy and security

reflexr serves many tenants from one process and one storage. It keeps them apart by construction, attributes every event to an actor your application authenticated, and bounds what events, rules and agents can set off. Authentication itself is yours. This page describes what the library enforces, what it leaves to you, and where to be careful.

## Tenants and workspaces

A tenant is the top-level isolation boundary: an organization, a customer or a team, as your application defines it. Each tenant has any number of workspaces, and each workspace has its own log, rule progress, runs and dead letters ([ADR-0016](../adr/0016-tenants-and-workspaces-like-artifactr.md)).

Isolation comes from scoped handles. `Workspaces.open(tenant_id, workspace_id, actor=...)` is the only place a tenant id enters. The `Workspace` it returns is bound to that tenant, that workspace and one actor, and every storage call it makes is scoped to them. Nothing below the handle accepts a tenant id, so application code cannot write a read that crosses tenants by mistake, and the same workspace id in two tenants names two separate workspaces:

```python
acme = await workspaces.open("acme", "prod", actor=SourceActor(name="grafana"))
globex = await workspaces.open("globex", "prod", actor=SourceActor(name="grafana"))

await acme.publish(ServiceError(service="auth", severity=8))
assert await globex.read() == []
```

The reactor works the same way: it evaluates each workspace under its own lease, and a run's action gets a handle on its own workspace only. In SQL storage every table's primary key starts with the tenant and the workspace, and every query filters on both ([Storage](storage.md#sql-storage)); a database-level guard, such as PostgreSQL row-level security, can be layered underneath as defence in depth.

A workspace is also the unit of access. Anyone who may use a workspace reads its whole log, over REST, the WebSocket or MCP, so put events with different audiences in different workspaces.

Code rules, schedules and the event allowlist are your application's code, not a tenant's data. They belong to the `Workspaces` object, and every tenant's workspaces evaluate the same code rules. So **every client of any tenant that `authorize` allows can read every code rule and schedule definition**: `GET /rules`, `GET /schedules` and the MCP `list_rules` tool return them, with their names, descriptions, conditions, scopes, action names and timetables. They read across the tenant, so they ask `authorize` for `reflexr:read_rules` or `reflexr:read_schedules` with no workspace, and an application can keep them from some members. The one exception is a schedule's targets, which name workspaces: `GET /schedules` narrows a schedule that targets particular workspaces to the caller's tenant's, and leaves out a schedule that targets none of them, so no tenant sees another's ids. Keep secrets and anything tenant-specific out of code rules and schedules, such as a customer's name in a rule's description or condition.

[Stored rules](rules.md#stored-rules) are a tenant's data. Each belongs to the one workspace it was installed in, and is keyed by its tenant and workspace like the log, so **a stored rule is never listed to another tenant**, nor to another workspace of its own tenant. `GET /rules` and `list_rules` leave stored rules out. A workspace's own reads, `GET /workspaces/{workspace_id}/rules`, `GET /workspaces/{workspace_id}/rules/{rule}`, and MCP's `rule_status` and `get_rule`, show its stored rules, with their versions and provenance, to whoever may use the workspace; another tenant's workspace of the same id has no rule of that name ([ADR-0055](../adr/0055-reading-stored-rules.md)).

Reading or writing another tenant's data through the public API is a vulnerability; please [report it](../../project/security.md) if you find a way.

## Authentication

Each surface asks your application who is calling:

| Surface | Hook | Returns |
|---|---|---|
| REST and WebSocket | `resolve_actor(connection)` | The tenant and the actor, or raises `Unauthorized` (401, or close code 4401) |
| MCP | `resolve(ctx)` | The tenant and the `ExternalAgentActor`, or raises |
| Your own code: webhooks, consumers, jobs | `workspaces.open(tenant_id, workspace_id, actor=...)` | A handle you authenticated for |

The tenant and the actor come from these hooks, never from a request body, a client's frames or a tool's arguments, so a client cannot act for someone else or reach another tenant by changing its request. That makes the hooks the boundary: verify a session, token, API key or webhook signature there, and derive the tenant from the verified identity. Headers, query parameters, `ctx.headers` and names are claims until you have checked them. [Serving over REST and WebSocket](serving.md#authentication) and [External agents over MCP](mcp.md#mounting-the-server) show both hooks.

Return the actor kind that says who is calling: `UserActor` for a person, `SourceActor` for a system that publishes events, such as a monitoring service, and `ExternalAgentActor` for an MCP client. `AgentActor` and `SystemActor` belong to reflexr's runs and to the reactor and schedules; the library records them itself, so a resolver should never return them.

## Authorization

Within a tenant, decide who may do what with an `authorize(tenant_id, workspace_id, actor, access)` hook, which `Workspaces` holds ([ADR-0056](../adr/0056-access-asked-in-every-workspace-method.md)). Every `Workspace` method asks it before it reads or writes anything, with the action it takes (`access.action`, one of `reflexr.workspace.ACTIONS`) and the rule it names, if any. Every surface reaches storage through those methods, so every REST request, WebSocket command, MCP tool call, resource read and subscription, and in-process call is asked by the same hook; none takes a hook of its own. Over REST, a refusal answers 403; the WebSocket closes with 4403 if it may not open the workspace or read its log, and answers a refused command with a `forbidden` result; MCP fails the tool call, or the read or subscription, with the same message. Without it, any authenticated actor may do anything in every workspace of its own tenant.

Every operation a client can perform is a command with its own action, and every command is attributed to the handle's actor in the log: who retried, skipped or cancelled a run, who replayed a rule, and who gave feedback ([ADR-0024](../adr/0024-causal-chains-and-operator-actions.md)). So some actors may publish (`reflexr:publish`) without operating runs (`reflexr:retry_run`, `reflexr:skip_run`, `reflexr:cancel_run`).

Changing a stored rule is behaviour that runs in the workspace. `install_rule`, `update_rule`, `archive_rule` and `replay_rule` are commands like any other, and `authorize` hears each with the rule's name in `Access.rule`; without `StoredRules`, every change is `forbidden`, and so is any change to a code rule's name ([ADR-0053](../adr/0053-stored-rules-one-fixed-configuration.md)). Admit as few actors as you can, such as only the bridge's run that installs a rule a person accepted.

A subscription, the WebSocket's or an MCP client's, is asked when it opens. Each command on it is asked as it arrives, so a revoked actor's next command is refused, but events keep flowing until the subscription closes. A rule's runs act as `AgentActor(rule=...)`, and are asked as it; the reactor's own work, evaluating rules, claiming runs and ticking schedules, is beneath the hook.

## What clients can publish

- **The event allowlist.** `Workspaces(storage, events=[ServiceError, Deploy, Heartbeat])` accepts those types only. Publishing any other type is rejected with `not_found`, even a type registered elsewhere in the process, so clients cannot publish arbitrary types. Without `events`, every type in the workspaces' registry is accepted; pass the list in production.
- **Run-only events.** `Workspaces(emitted=[IncidentOpened])` names types that only runs may publish. A client, over REST, the WebSocket, MCP or a handle of your own that no run caused, is refused with `forbidden`, so an incident, a verdict or anything else your workflows produce cannot be forged from outside.
- **Reserved events.** `Workspaces(publishers={"artifactr": [SourceActor(name="artifactr")]})` reserves a namespace, or a type, to the actors that alone may publish it, compared by `participant`. Anyone else, runs included, is refused with `forbidden`, so a bridge's or an integration's events can't be forged by another client. The check sits beneath `authorize`, so no grant overrides it. It relies on your `resolve_actor` and `resolve` never resolving a client to a reserved source ([ADR-0057](../adr/0057-reserved-publishers.md)).
- **reflexr's own events are never published.** `reflexr:rule_fired`, `reflexr:run_succeeded`, `reflexr:feedback_given`, `reflexr:tick` and the rest are recorded by reflexr alone, and publishing one is rejected with `forbidden`, so no client can forge a firing, a run's outcome or a schedule's tick.
- **Events are validated.** An event must match its type's schema, and unknown fields are rejected, so a producer's typo fails loudly rather than never matching a rule.
- **Ids make publishing idempotent,** within a workspace. A replayed request with the same id appends nothing.

```text
not_found: event type debug.dump does not exist
forbidden: reflexr:run_succeeded events are recorded by reflexr, not published
```

## Keeping agents in bounds

Rules run agents on events that the outside world wrote, so treat event data as untrusted input to the model, like any user message. The prompt of an `AgentAction` describes the events that made its rule fire, and `EventContext`'s `read_events` tool shows the model more of the log. Decide what the agent may do with that in mind:

- **Emit allowlists.** `EventContext(emit=[IncidentOpened])` lets the agent publish only the listed types, validated against their schemas, and an agent with no `emit` list cannot publish at all ([Actions](actions.md#agents)).
- **Least privilege in actions.** Actions run with your application's dependencies (`reaction.deps`). Give them only what they need, and check permissions in the action or tool, not only in the prompt.
- **The model gateway.** Model spend and content controls, such as per-tenant keys, budgets and guardrails, live in the [LLM gateway](gateway.md). Keys come from your secret store and never appear in the log or on spans.

## Stored rules

A stored rule is behaviour a tenant adds at runtime, so reflexr bounds what one can do whoever `authorize` lets install it:

- **Only registered code runs.** A stored rule may name only the actions in `StoredRules.actions`, with params checked against their models, and has no predicates and no `matches` operator, whose regular expressions could run without a timeout while the workspace's lock is held.
- **Its cost is bounded.** A throttle of at most 60 firings an hour is required, over the whole rule, since a stored rule has no scope fields; retries, the timeout, windows, the description and the rule's size are bounded, and a workspace has at most 50 active stored rules. The action's usage limits and the tenant's gateway budget apply as for any run.
- **Its loops are bounded.** No rule field can raise the depth limit, and `reflexr:rule_installed` continues the causal chain of whatever installed the rule.
- **Its text is untrusted.** A rule's description reaches agents' prompts, so treat it as you treat event data, and keep the gateway's guardrails on.
- **Provenance is a claim.** reflexr records it unread, beside the actor that made the change, which your application authenticated. Check what it says before acting on it, as relayr re-reads artifactr before it installs a rule.
- **Operators see the names.** A stored rule's name reaches spans, Langfuse and LiteLLM metadata, which are operators' tools, not tenants'. Metrics record its namespace, such as `chat:*`, not its name.

## Limits

Events that set off workflows can loop and can spend. The library bounds both, and [Loop and spend safety](safety.md) covers each limit in detail ([ADR-0010](../adr/0010-loop-and-spend-safety.md)):

| Limit | Where | Default |
|---|---|---|
| Causation depth: how many runs a chain of events may pass through | `Workspaces(max_depth=...)` | 8 |
| Throttles: how often a rule may fire per scope | `.at_most(times, per=...)` on a rule's condition | None |
| Attempts and backoff per run | `Rule(retry=RetryPolicy(...))` | 5 attempts |
| How long one attempt may take | `Rule(timeout=...)` | None |
| Runs executing at once, per reactor | `Reactor(concurrency=...)` | 10 |
| Requests and tokens per agent attempt | `AgentAction(usage_limits=UsageLimits(...))` | None |
| What a stored rule may be: its throttle, retries, timeout, windows, size, and how many a workspace has | Constants in `reflexr.core`, checked by `check_stored` | Fixed ([Stored rules](rules.md#stored-rules)) |

A rule whose action triggers itself stops at the depth limit: with `max_depth=3`, a rule that answers each `oncall:incident.opened` by emitting another fires three times, and the firing that would go deeper is refused and dead-lettered for that rule, with the reason `the firing would be at causation depth 4, beyond the limit of 3`. A run's handle that tries to publish beyond the limit is rejected with `depth_exceeded`.

The WebSocket closes connections that do not say `hello` within `hello_timeout` (10 seconds), and disconnects clients whose outbox exceeds `outbox_size` frames (1,000) instead of buffering without bound; a disconnected client resumes from the log without losing anything. The library does not limit request sizes, publishing rates or the number of workspaces a tenant creates, and a workspace comes into being the first time something is published to it. Enforce those in your application or at your proxy.

## Reporting vulnerabilities

Report vulnerabilities privately, as described in the [security policy](../../project/security.md).
