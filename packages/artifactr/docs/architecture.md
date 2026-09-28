# Architecture

> **Status:** accepted design, being built in the phases tracked by [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). This document is evergreen: it is updated in the same pull request as the code that changes it, and the table below shows what exists today. Decisions are recorded in [`adr/`](adr/README.md), proposals in [`rfcs/`](rfcs/README.md), and the wire protocol in [`protocol.md`](protocol.md).

| Package | Status |
|---|---|
| `artifactr.core` | Implemented |
| `artifactr.workspace` | Planned (phase 2) |
| `artifactr.agent` | Planned (phase 3) |
| `artifactr.sql` | Planned (phase 4) |
| `artifactr.fastapi`, `artifactr.mcp` | Planned (phase 5) |
| `examples/docplan` | Planned (phase 6) |

## What artifactr is

artifactr is a Python library for building chat applications in which a person and an agent collaborate through **shared, mutually editable artifacts**: documents, plans, specs, datasets, anything with structure.

The chat is one channel of communication. The artifacts are a second one. When the agent restructures a plan, or a person rewrites a paragraph the agent drafted, the edit says something about how each side is thinking. artifactr makes those edits first-class: versioned, attributed to whoever made them, visible to every participant, and fed back into the agent's context.

The library provides the machinery; applications provide the artifact types. A reference implementation, [`examples/docplan`](#build-plan) (a Markdown document plus a structured plan), is built on the library's public API as one implementation of it.

### Goals

- Downstream projects define an artifact type by subclassing a Pydantic model. Versioning, conflict handling, change history, agent tools and transports come from the library.
- Every change, from any participant, takes the same path and produces the same events.
- The agent always knows what changed since it last looked, and who changed it.
- Multi-tenant, with many concurrent chats sharing a workspace's artifacts.
- Idiomatic use of Pydantic, pydantic-ai, SQLAlchemy, FastAPI and the MCP SDK, rather than parallel abstractions next to them.
- Small: six core concepts, readable in an afternoon.

### Non-goals (for now)

- Character-level real-time co-editing (CRDTs). Optimistic concurrency with patches covers turn-based collaboration; CRDT-backed types can come later behind the same interfaces.
- A frontend. The protocol is specified and typed; applications build their own UIs.
- Hosting or deployment tooling.

## Core concepts

| Concept | What it is |
|---|---|
| **Actor** | Who did something: a user, the built-in agent (per run), an external agent connected over MCP, or the system. Every event is attributed to one. |
| **Artifact** | A Pydantic model subclass that defines one artifact type. Stored instances are `Versioned[T]`: the data plus its id, version and last actor. |
| **Command** | An intent to change the workspace: edit an artifact, propose an edit, answer a proposal, post a message. Commands can be rejected. |
| **Event** | A fact that happened, appended to the workspace's log with a sequence number (`seq`). Events are never rejected or rewritten. |
| **Workspace** | A tenant-scoped handle over artifacts, threads and the event log. The only way to read or write. |
| **Session** | The pydantic-ai dependencies for one agent run: a workspace handle bound to the agent's actor, the thread, the artifacts in focus, and the application's own deps. |

Supporting types: `Envelope` (an event plus its `seq`, actor, timestamp and scope), `Proposal` (a suggested change awaiting a decision), and `Thread` (a chat).

## Layers

```mermaid
graph TD
    app["Your application"] --> fastapi["artifactr.fastapi<br/>WebSocket + REST"]
    app --> mcp["artifactr.mcp<br/>MCP server"]
    app --> agent
    fastapi --> agent["artifactr.agent<br/>pydantic-ai capability"]
    fastapi --> workspace
    mcp --> workspace
    agent --> workspace["artifactr.workspace<br/>scoped handles, storage protocols"]
    sql["artifactr.sql<br/>SQLAlchemy storage"] --> workspace
    workspace --> core["artifactr.core<br/>pure, synchronous rules"]
```

Dependencies point one way. Each layer is usable without the ones above it.

| Package | Depends on | Responsibility |
|---|---|---|
| `artifactr.core` | pydantic, jsonpatch | Every rule. Pure, synchronous, no I/O, no pydantic-ai. |
| `artifactr.workspace` | core | `Workspaces`, `Workspace`, storage protocols, in-memory storage. |
| `artifactr.sql` (extra) | workspace, SQLAlchemy 2 async | Durable storage and migrations. |
| `artifactr.agent` | workspace, pydantic-ai | The `ArtifactWorkspace` capability, `Session`, live-output helpers. |
| `artifactr.fastapi` (extra) | agent, FastAPI | The thread protocol over WebSocket, and REST commands. |
| `artifactr.mcp` (extra) | workspace, mcp | Artifacts as MCP resources, commands as MCP tools. |

### `artifactr.core`: sans-IO

Core holds every rule as plain functions over immutable values. Storage and transport belong to the host, which asks core what to load, loads it, lets core decide, and saves what core returns inside its own transaction ([ADR-0018](adr/0018-core-host-contract.md)):

```python
state = State()
while missing := core.needs(command, actor=actor, state=state):
    state = load(missing, into=state)  # the host's I/O
result = core.commit(command, state, actor=actor)  # CommitResult, or raises a Rejection
save(result)  # entities and events, in one transaction
```

- `needs` returns the ids of the artifacts, proposals, threads and runs a command depends on. Some commands only know their full needs once their first entities are loaded (accepting a proposal needs the proposal before it knows which artifact), so hosts loop until nothing is missing.
- `commit` decides a command. For artifact changes it applies the type's write policy, checks the base version, applies the patch, and validates the result against the type. It returns a `CommitResult`: the outcome (`Applied`, `Proposed`, `Resolved` or `Recorded`), the entities to save, the revisions to append, and the events to log. Accepting or rejecting a proposal is the `RespondToProposal` command; an accepted change is rebased onto the artifact's current version, with the person's own changes layered on top.
- `record` decides a fact about an agent run (`RunStarted`, `ToolCalled`, `ToolReturned`, `RunPaused`, `RunEnded`) or an application `AppEvent`. Only the thread's own agent, or the system, may record facts about its runs.
- `change_notes` turns a slice of the log into short, attributed notes for a viewer. It keeps changes by other participants to the artifacts the viewer follows (and artifacts created in the viewer's thread), proposals others made on them, and decisions on the viewer's own proposals; several changes to one artifact become one note.
- `resume` decides where a reconnecting client's replay starts, and whether it must reset because it has seen events the log does not have.

Commands carry the ids of everything they create, including the proposal id to use if a write policy turns the change into a proposal. The same command against the same state therefore always yields the same result. Ids are plain strings; aliases such as `ArtifactId` document intent.

Rejections are exceptions with a stable `code` and typed details: `VersionConflict` (`base`, `head`), `ValidationFailed` (Pydantic's `errors`), `PatchFailed`, `NotFound` (`entity`, `id`), `Forbidden`, `InvalidState`, and `UnsupportedProtocol`. Their `payload()` is what the protocol sends to clients.

Because core is pure, its behaviour is pinned by a **conformance suite** of JSON fixtures in `tests/conformance/cases/`: given an actor, the entities that exist and a command, expect these events and entities or this rejection. The fixtures are the language-neutral specification. Any future port of core, or a hot path rewritten as a native extension, must pass them.

Core events form a **closed** discriminated union (`KnownEvent`), so pyright checks `match event:` blocks ending in `assert_never` for exhaustiveness. Applications extend the log through one **open** family, `AppEvent`. An event type from a newer protocol version validates as `UnknownEvent` rather than failing, and round-trips unchanged. This mirrors how pydantic-ai separates its own events from application `CustomEvent`s.

### Defining an artifact type

```python
from typing import ClassVar, Literal, Self

from pydantic import BaseModel

from artifactr import Artifact, MarkdownArtifact, WritePolicy, new_id


class Task(BaseModel):
    title: str
    status: Literal["todo", "doing", "done"] = "todo"


class Plan(Artifact):  # registered as "plan"
    write_policy: ClassVar[WritePolicy] = "propose"

    goal: str = ""
    tasks: dict[str, Task] = {}  # keyed by id, so patch paths stay stable

    def add_task(self, title: str) -> str:
        task_id = new_id()
        self.tasks[task_id] = Task(title=title)
        return task_id

    def render_for_agent(self) -> str:
        lines = [f"Goal: {self.goal}"]
        lines += [f"- [{t.status}] {t.title} ({tid})" for tid, t in self.tasks.items()]
        return "\n".join(lines)

    def describe_change(self, before: Self) -> str | None:
        done = [
            t.title
            for tid, t in self.tasks.items()
            if t.status == "done" and tid in before.tasks and before.tasks[tid].status != "done"
        ]
        return f"completed {', '.join(done)}" if done else None


class Doc(MarkdownArtifact):  # registered as "doc"; edited with anchored text replacements
    pass
```

Registration happens in `__pydantic_init_subclass__`, Pydantic's hook that runs after the model's fields are built. The type name is derived from the class name in snake case and can be overridden with `class Plan(Artifact, name="...")`, the same convention pydantic-ai uses for `CustomEvent`. Intermediate base classes pass `abstract=True`. `describe_change(before)` is an optional hook that summarizes a change in the type's own words; without it, the summary is generated from the patch.

The library defines the patch kinds:

- **JSON Patch** (RFC 6902) for `Artifact` subclasses. `Versioned[T].edit(fn)` copies the data, lets `fn` mutate the copy, and diffs the result into a patch against the current version.
- **Anchored text edits** for any text field, such as a `MarkdownArtifact`'s `text`. Each edit replaces an exact string that must occur exactly once, the edit form language models perform most reliably. An empty anchor writes into an empty field.

Agents do not write raw JSON Patch. They get domain tools from the application (`add_task`, `set_status`) or the generic text-edit tool for documents, and those tools produce patches.

```python
plan = await ws.get(Plan, plan_id)  # Versioned[Plan]
outcome = await ws.commit(plan.edit(lambda p: p.add_task("Ship v1")))
```

## Data model

```mermaid
erDiagram
    TENANT ||--o{ WORKSPACE : owns
    WORKSPACE ||--o{ ARTIFACT : contains
    WORKSPACE ||--o{ THREAD : contains
    WORKSPACE ||--o{ EVENT : "log ordered by seq"
    ARTIFACT ||--o{ REVISION : "append-only"
    ARTIFACT ||--o{ PROPOSAL : "suggested changes"
    THREAD }o--o{ ARTIFACT : "focuses on"
    THREAD ||--o{ RUN : "one active at a time"
```

- **Artifacts belong to the workspace**, not to a chat, so several chats and people can work on the same plan. A thread lists the artifacts it is focused on.
- **Revisions are append-only.** Every committed change writes a revision with its version, patch, resulting data and actor. Reverting writes a new revision; versions never go backwards.
- **One event log per workspace**, with a single gap-free `seq`. Events carry an optional `thread_id` and `run_id`, and subscribers filter on them.
- **Proposals** are durable objects that wrap the command they would execute (create, edit or archive), with its base version, the proposer and a rationale.
- **Model history** (pydantic-ai `ModelMessage`s, serialized with `ModelMessagesTypeAdapter`) is stored per thread next to the log, not reconstructed from it.

## The write path

Every change, whether from the built-in agent, a person in a UI, an external agent over MCP, or a script, goes through one path.

```mermaid
sequenceDiagram
    participant A as Actor (agent tool, REST, WebSocket, MCP)
    participant W as Workspace
    participant C as core
    participant S as Storage (host transaction)
    participant L as Subscribers
    A->>W: commit(command)
    W->>S: begin, load current state
    W->>C: commit(command, current, actor)
    alt accepted
        C-->>W: revisions and events
        W->>S: save revisions, assign seq, append events, commit
        W-->>A: Applied or Proposed
        S-->>L: new envelopes (subscribe after_seq)
    else rejected
        C-->>W: raises VersionConflict, ValidationFailed, ...
        W->>S: rollback
        W-->>A: raises the rejection
    end
```

`Workspace.commit` returns the command's outcome with the `seq` of its last event: `Applied(artifact_id, version)` when a change was written, `Proposed(proposal_id)` when the artifact type's write policy turned it into a proposal, `Resolved(proposal_id, decision, version)` for an answered proposal, and `Recorded()` for everything else. Run lifecycle facts (a run started, a tool was called) are recorded through `Workspace.record`, which calls `core.record` under the same transaction and sequencing. Nothing else writes to storage.

As a result:

- No surface has its own copy of accept, merge or validation logic.
- A person's edit is as visible to the agent as the agent's edit is to the person.
- The host's transaction can include its own tables, because core never touches storage.

## The agent

artifactr plugs into pydantic-ai as one **capability**, `ArtifactWorkspace`. A turn is an ordinary `agent.run(...)`; there is no custom runner, and the capability composes with any others the application uses.

```python
agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    toolsets=[plan_tools],
    capabilities=[ArtifactWorkspace(types=[Doc, Plan])],
)
```

| Capability hook | What `ArtifactWorkspace` does |
|---|---|
| `get_toolset` | Generic tools: list, read, edit document text, propose. Application toolsets are registered on the agent itself ([ADR-0017](adr/0017-application-toolsets-and-capability-events.md)). |
| `get_instructions` | Renders focused artifacts with `render_for_agent`, fresh from storage. Lists currently available actions as text, so tool definitions never change and the prompt cache stays warm. |
| `before_run` | Records `run_started` and the user's message. Adds change notes since the thread's last-seen `seq` to the prompt. |
| `for_run` | Subscribes to the workspace log for the duration of the run. Other actors' changes to focused artifacts, and new messages in this thread, are delivered into the live run with `ctx.enqueue(priority="asap")`. |
| `on_tool_execute_error` | Turns `VersionConflict` into `ModelRetry` with a summary of what changed, so tools never catch it themselves. |
| `on_event` | Records tool calls and results as durable events. |
| `after_run`, `on_run_error` | Stores the run's new `ModelMessage`s, records the final assistant message, and records `run_ended` with its status and usage. |

Tools are plain pydantic-ai tools over `RunContext[Session]`:

```python
plan_tools = FunctionToolset[Session[AppDeps]]()


@plan_tools.tool
async def add_task(ctx: RunContext[Session[AppDeps]], plan_id: str, title: str) -> str:
    """Add a task to a plan."""
    plan = await ctx.deps.workspace.get(Plan, plan_id)
    match await ctx.deps.workspace.commit(plan.edit(lambda p: p.add_task(title))):
        case Applied(version=version):
            return f"Added. The plan is now at version {version}."
        case Proposed(proposal_id=proposal_id):
            return f"Proposed adding the task ({proposal_id}); the user will review it."
```

Application tools emit ephemeral progress, such as a draft of an artifact being generated, with `ctx.emit(...)` and a pydantic-ai `CustomEvent` subclass. artifactr's own tools and hooks emit `CapabilityEvent`s in the `artifactr` namespace, as pydantic-ai requires of capabilities ([ADR-0017](adr/0017-application-toolsets-and-capability-events.md)). Both reach the live channel only, never the log.

### Change notes and steering

- When a run starts, the agent receives notes such as *"alice edited plan-1 (v7 → v8): marked 'Ship v1' done; added task 'Write changelog'."* Notes cover only the artifacts the thread is focused on and exclude the agent's own changes.
- While a run is active, the same notes, and any new message the person sends in the thread, are enqueued into the live run and reach the model at its next request. A person can steer a long run without stopping it.
- Focused artifacts are rendered from storage, never cached across runs or connections.

### Proposals and pausing

- Each artifact type declares a `write_policy`: `"direct"` or `"propose"`. A thread can be switched into suggest mode, which forces proposals for every type.
- Proposals do not block the run. The agent keeps working; the person accepts, rejects or edits the proposal whenever and from any surface; the outcome reaches the agent as a change note. When a proposal is accepted with edits, the note includes the person's changes as a diff.
- Blocking points, such as a question the agent needs answered or a tool that requires approval, use pydantic-ai's deferred tools (`CallDeferred`, `ApprovalRequired`). The run ends with `DeferredToolRequests`, recorded as `run_paused`. When the answers arrive from any surface, the host resumes with `agent.run(..., deferred_tool_results=...)` under the same artifactr `run_id`. The pause survives restarts because nothing waits in memory.

## Live output

The event log carries durable domain events only. Token-level output belongs to whoever drives the run, passed as an independent parameter:

```python
async with ws.open_run(thread_id) as run:  # lease: one active run per thread
    await agent.run(
        prompt,
        deps=run.session,
        message_history=await run.history(),
        event_stream_handler=forward_live(channel),  # caller-owned
    )
```

`forward_live` maps pydantic-ai stream events (text and thinking deltas, tool-call argument deltas, and `CustomEvent`s emitted by tools) to the protocol's live frames and sends them to a `LiveChannel`:

- `WebSocketChannel`: the connection that started the run.
- `FanoutChannel`: in-process fan-out keyed by `run_id`, so other clients watching the thread can attach.
- A pub/sub implementation (Redis, NATS) for fan-out across replicas, as an optional add-on.
- `NullChannel` for headless runs.

The run holds a lease, not a socket: if the connection that started it drops, the run continues and the channel detaches. Losing live frames is harmless, because the durable `message_posted`, `tool_returned` and `artifact_changed` events are authoritative. A client that reconnects mid-run replays the log from its last `seq` and reattaches to the run's live channel if the run is still active.

## Tenancy and concurrency

- **Scoped handles.** `await workspaces.open(tenant_id, workspace_id, actor=...)` returns a `Workspace` bound to that tenant, workspace and actor. Nothing below it accepts a raw tenant id, so a query that crosses tenants cannot be written. Postgres row-level security can be layered underneath as defence in depth.
- **Actors are bound to handles.** `ws.as_actor(agent_actor)` returns a handle for the agent, and commits through it are attributed to the agent.
- **Optimistic concurrency.** Every edit names the version it was based on. A stale edit is rejected with the changes made since, so the agent retries against fresh state and a UI can rebase or ask the person.
- **One active run per thread**, enforced by a lease (`thread.active_run_id` with an expiry) that works across replicas. Concurrency happens across threads. A message sent during a run steers it instead of queueing.
- **Sequencing.** `seq` is assigned inside the commit transaction (`UPDATE workspace SET head_seq = head_seq + :n RETURNING head_seq`), giving a gap-free total order per workspace. This serializes commits within one workspace; tokens are not in the log, so commit volume stays modest.

## Surfaces

| Surface | Package | Role |
|---|---|---|
| WebSocket | `artifactr.fastapi` | The thread protocol: subscribe to a workspace log with resume, send commands, receive live frames for runs. See [`protocol.md`](protocol.md). |
| REST | `artifactr.fastapi` | The same commands as HTTP endpoints, plus reads. Commands go through the same `Workspace.commit` and publish the same events. |
| MCP | `artifactr.mcp` | External agents join the workspace as actors. Artifacts are resources, commands are tools, and change notifications flow through the MCP SDK's `SubscriptionBus`, fed by the log. Mounted on the application with `MCPServer.streamable_http_app()`. |

pydantic-ai's AG-UI and Vercel AI adapters may be added later as compatibility surfaces for simple frontends. They are request-scoped with client-supplied state, so they sit beside the thread protocol rather than replacing it.

## Storage protocols

```python
class Storage(Protocol):
    def transaction(self, scope: Scope) -> AbstractAsyncContextManager[Transaction]: ...
    async def read(self, scope: Scope, *, after_seq: int, limit: int) -> list[Envelope]: ...
    def subscribe(
        self, scope: Scope, *, after_seq: int, where: EventFilter | None = None
    ) -> AsyncIterator[Envelope]: ...


class Transaction(Protocol):
    async def load(self, artifact_id: ArtifactId) -> Versioned[Artifact] | None: ...
    async def save(self, result: CommitResult) -> list[Envelope]: ...  # assigns seq
```

Alongside `Storage`, the workspace layer defines `HistoryStore` (a thread's `ModelMessage`s) and `RunLeases`. Two implementations of each ship:

- **In-memory**, for tests and examples. Subscribers wait on an `asyncio.Condition`.
- **SQLAlchemy 2 async** (`artifactr.sql`), with Alembic migrations. Subscribers use Postgres `LISTEN/NOTIFY`, or polling on SQLite.

`subscribe(after_seq=...)` is the only read path for replay, live fan-out, hooks, MCP notifications and change notes. Because a subscription starts from a `seq`, there is no gap to manage between replaying history and following live events.

## Dependencies

| Dependency | Used for | Current major (2026-09) |
|---|---|---|
| pydantic | Artifact types, commands, events, JSON Schema | 2.13 |
| jsonpatch | RFC 6902 apply and diff in core | 1.33 |
| pydantic-ai-slim | Agent runtime: capabilities, toolsets, deferred tools, message history | 2.51 |
| SQLAlchemy (asyncio) | SQL storage | 2.1 |
| FastAPI | WebSocket and REST adapter | 0.141 |
| mcp | MCP server (`MCPServer`, subscriptions) | 2.2 |

Python 3.12+. Tooling: uv, ruff, pyright in strict mode, pytest.

Observability uses pydantic-ai's built-in OpenTelemetry instrumentation. The capability adds tenant, workspace, thread and run as span attributes.

## Testing

- **Core:** conformance fixtures, plus property tests (hypothesis) that patches round-trip: applying `diff(a, b)` to `a` gives `b`.
- **Workspace:** one suite runs against both in-memory and SQL storage.
- **Agent:** scripted runs with pydantic-ai's `TestModel` and `FunctionModel`, so no test calls a model API. Assertions are on the events written, including conflicts, steering and deferred pauses.
- **Adapters:** WebSocket contract tests with FastAPI's `TestClient`, and an MCP client round-trip.
- **Protocol:** the JSON Schema in `schemas/` is generated from the models and checked in. CI fails if it drifts.

## Build plan

The phases, their exit criteria and their progress are tracked in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md).

1. `artifactr.core` and its conformance fixtures.
2. `artifactr.workspace` with in-memory storage.
3. `artifactr.agent` on pydantic-ai 2.x.
4. `artifactr.sql` and migrations.
5. `artifactr.fastapi` and `artifactr.mcp`, plus protocol schema generation.
6. `examples/docplan` and the CLI.
7. The documentation website and brand.

## Decisions

| ADR | Decision |
|---|---|
| [0001](adr/0001-python-library-with-sans-io-core.md) | Python library with a sans-IO core |
| [0002](adr/0002-single-write-path.md) | One write path: commands through `Workspace.commit` |
| [0003](adr/0003-artifact-types-as-pydantic-subclasses.md) | Artifact types are Pydantic subclasses with library-defined patch kinds |
| [0004](adr/0004-optimistic-concurrency-and-revisions.md) | Optimistic concurrency and append-only revisions |
| [0005](adr/0005-one-event-log-per-workspace.md) | One durable event log per workspace |
| [0006](adr/0006-agent-integration-as-pydantic-ai-capability.md) | Agent integration as a pydantic-ai capability |
| [0007](adr/0007-caller-owned-live-output.md) | Live output is owned by the caller, not the log |
| [0008](adr/0008-agent-perception-and-steering.md) | Agent perception: change notes, fresh rendering, steering |
| [0009](adr/0009-write-policies-and-non-blocking-proposals.md) | Write policies and non-blocking proposals |
| [0010](adr/0010-pausing-with-deferred-tools.md) | Pausing with pydantic-ai deferred tools |
| [0011](adr/0011-workspace-scoped-artifacts-and-tenant-handles.md) | Workspace-scoped artifacts and tenant-scoped handles |
| [0012](adr/0012-surfaces-websocket-rest-mcp.md) | Surfaces: WebSocket thread protocol, REST commands, MCP |
| [0013](adr/0013-library-with-reference-implementation.md) | A library with adapters and a reference implementation |
| [0014](adr/0014-trunk-based-development-with-rfcs-and-adrs.md) | Trunk-based development with RFCs, ADRs and evergreen docs |
| [0015](adr/0015-quality-gates.md) | Quality gates |
| [0016](adr/0016-mit-license.md) | MIT license |
| [0017](adr/0017-application-toolsets-and-capability-events.md) | Application toolsets register on the agent; the capability emits capability events |
| [0018](adr/0018-core-host-contract.md) | Core's host contract: needs, commit and record |

## Open questions

- **Log retention.** When old envelopes are compacted, `resume` falls back to a snapshot. The snapshot format is not yet specified.
- **Very hot workspaces.** Assigning `seq` serializes commits per workspace. If that becomes a bottleneck, the log could be sharded by artifact group behind the same per-workspace cursor.
- **Change-note volume.** With many concurrent chats, notes may need coalescing beyond focus filtering.
- **Crash recovery for runs.** A run interrupted by a process crash is recorded as failed when its lease expires. pydantic-ai's durable execution integrations (Temporal, DBOS, Prefect) could make such runs resumable.
- **`jsonpatch` maintenance.** It is stable but rarely updated; its surface is small enough to vendor if needed.
