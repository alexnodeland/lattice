# Architecture

> **Status:** v0.1 is built, as planned in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and released as 0.1.0. [RFC-0002](rfcs/0002-observability-feedback-and-evaluation.md) has since added observability, typed feedback, the LLM gateway, and the `[evals]` extra over evalr. This document is evergreen: it is updated in the same pull request as the code that changes it, and the table below shows what exists today. Decisions are recorded in [`adr/`](adr/README.md), proposals in [`rfcs/`](rfcs/README.md), and the wire protocol in [`protocol.md`](protocol.md).

| Package | Status |
|---|---|
| `artifactr.core` | Implemented |
| `artifactr.telemetry` | Implemented: spans, attribution and the metric registry ([RFC-0002](rfcs/0002-observability-feedback-and-evaluation.md)) |
| `artifactr.workspace` | Implemented, with in-memory storage |
| `artifactr.agent` | Implemented |
| `artifactr.scores` | Implemented: the mirror that scores feedback, on evalr's mapping and ports |
| `artifactr.sql` | Implemented, on PostgreSQL and SQLite |
| `artifactr.fastapi`, `artifactr.mcp` | Implemented |
| `artifactr.otel`, `artifactr.langfuse`, `artifactr.litellm` | Implemented: the OpenTelemetry SDK, Langfuse and LiteLLM adapters |
| `artifactr.evals` | Implemented: datasets from the log, experiments, online evaluation and the end-to-end measures, over evalr |
| `examples/docplan` | Implemented: server, terminal client and tests; observed, rated and routed when configured |

## What artifactr is

artifactr is a Python library for building chat applications in which a person and an agent collaborate through **shared, mutually editable artifacts**: documents, plans, specs, datasets, anything with structure.

The chat is one channel of communication. The artifacts are a second one. When the agent restructures a plan, or a person rewrites a paragraph the agent drafted, the edit says something about how each side is thinking. artifactr makes those edits first-class: versioned, attributed to whoever made them, visible to every participant, and fed back into the agent's context.

The library provides the machinery; applications provide the artifact types. A reference implementation, [`examples/docplan`](https://github.com/alexnodeland/artifactr/tree/main/examples/docplan) (a Markdown document plus a structured plan), is built on the library's public API as one implementation of it ([ADR-0024](adr/0024-reference-implementation-as-a-workspace-member.md)).

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
| **Actor** | Who did something: a user, the built-in agent (per run), an external agent connected over MCP, the system, or an evaluator. Every event is attributed to one. |
| **Artifact** | A Pydantic model subclass that defines one artifact type. Stored instances are `Versioned[T]`: the data plus its id, version and last actor. |
| **Command** | An intent to change the workspace: edit an artifact, propose an edit, answer a proposal, post a message. Commands can be rejected. |
| **Event** | A fact that happened, appended to the workspace's log with a sequence number (`seq`). Events are never rejected or rewritten. |
| **Workspace** | A tenant-scoped handle over artifacts, threads and the event log. The only way to read or write. |
| **Session** | The pydantic-ai dependencies for one agent run: a workspace handle bound to the agent's actor, the thread, the artifacts in focus, and the application's own deps. |

Supporting types: `Envelope` (an event plus its `seq`, actor, timestamp and scope), `Proposal` (a suggested change awaiting a decision), `Thread` (a chat), and `Feedback` (a typed judgement of an artifact version, a thread, a turn or a message).

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
    scores["artifactr.scores<br/>feedback as scores, on evalr"] --> workspace
    otel["artifactr.otel<br/>OpenTelemetry SDK"] --> telemetry
    langfuse["artifactr.langfuse<br/>Langfuse"] --> scores
    litellm["artifactr.litellm<br/>LiteLLM"] --> agent
    evals["artifactr.evals<br/>evalr"] --> agent
    workspace --> telemetry["artifactr.telemetry<br/>OpenTelemetry API"]
    telemetry --> core["artifactr.core<br/>pure, synchronous rules"]
```

Dependencies point one way. Each layer is usable without the ones above it.

The inner layers (core, telemetry, workspace, agent) form a hexagon of ports and adapters ([ADR-0034](adr/0034-ports-and-adapters-for-integrations.md)). A **port** is a small interface an inner layer owns: a `typing.Protocol` such as `Storage`, or an API that already plays the role, such as the OpenTelemetry API. An **adapter** implements a port in an extra's package, which imports its own libraries and the inner layers, never the other way round. The surfaces are driving adapters. `tests/test_layering.py` enforces all of it.

| Package | Depends on | Role | Responsibility |
|---|---|---|---|
| `artifactr.core` | pydantic, jsonpatch | Inner | Every rule. Pure, synchronous, no I/O, no pydantic-ai, no OpenTelemetry. |
| `artifactr.telemetry` | core, the OpenTelemetry API | Inner; its port is the OpenTelemetry API | Span attribution, the metric registry, and recording through the API. |
| `artifactr.workspace` | core, telemetry | Inner; owns the `Storage` port | `Workspaces`, `Workspace`, storage protocols, in-memory storage. |
| `artifactr.agent` | workspace, telemetry, pydantic-ai | Inner; owns the `TurnContext`, `TurnEvaluator` and `CommandResults` ports | The `ArtifactWorkspace` capability, `Session`, `Runner`, live-output helpers, and the memory of commands' results. |
| `artifactr.scores` (needs evalr, from the `langfuse` or `evals` extra) | workspace, evalr's core | Uses evalr's `ScoreSink` and `ScoreConfigStore` ports | Feedback as scores, named as each type is registered, and the mirror that records a workspace's feedback in a sink. |
| `artifactr.sql` (extra) | workspace, SQLAlchemy 2 async, Alembic | Adapter for `Storage` | Durable storage on PostgreSQL and SQLite, and its migrations. |
| `artifactr.otel` (extra) | telemetry, the OpenTelemetry SDK, exporters and instrumentations | Adapter for the OpenTelemetry API | `configure_telemetry`: providers, OTLP export, instrumentations and metric views, for applications. |
| `artifactr.litellm` (extra) | agent, pydantic-ai's OpenAI support | Adapter for pydantic-ai's `Model` | `litellm_model` and the `LiteLLMGateway` capability: each request's tenancy, session, trace, key and guardrails, and guardrail blocks as typed failures ([ADR-0043](adr/0043-the-litellm-adapter.md)). |
| `artifactr.langfuse` (extra) | scores, agent, langfuse, evalr's core | Adapter for evalr's `ScoreSink` and `ScoreConfigStore`, and for `TurnContext` | Feedback as Langfuse scores and score configs, a span filter that keeps whole traces, and each turn's trace attributes ([ADR-0039](adr/0039-the-langfuse-adapter.md)). |
| `artifactr.evals` (extra) | agent, evalr | Adapter for `TurnEvaluator`, and for evalr's `FeedbackSource` and experiment `Task` | Datasets from the log, experiments that replay turns, online evaluation of turns with verdicts recorded as feedback, and the end-to-end measures ([ADR-0044](adr/0044-the-evalr-adapter.md)). |
| `artifactr.fastapi` (extra) | agent, FastAPI | Driving adapter | The thread protocol over WebSocket, and REST commands. |
| `artifactr.mcp` (extra) | agent, mcp | Driving adapter | Artifacts as MCP resources, commands and reads as MCP tools. |

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
        task_id = new_id("task")
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
- **Trace links.** A run records the OpenTelemetry trace id of each attempt (`Run.trace_ids`, from the `trace_id` of each `run_started`), since a run that pauses and resumes runs once per attempt. A revision records the trace it was committed in (`Revision.trace_id`), stamped by the workspace. They let feedback on a turn or an artifact version find the trace it is about. Both are stored in the entities' JSON, so they need no schema change ([ADR-0033](adr/0033-trace-links-on-runs-and-revisions.md)).

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

artifactr plugs into pydantic-ai as one **capability**, `ArtifactWorkspace` ([ADR-0006](adr/0006-agent-integration-as-pydantic-ai-capability.md)). A turn is an ordinary `agent.run(...)`, and the capability composes with any others the application uses. A `Runner` drives runs in threads for the surfaces ([ADR-0020](adr/0020-running-agents-in-threads.md)).

```python
agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    toolsets=[plan_tools],  # the application's own tools
    capabilities=[ArtifactWorkspace(types=[Doc, Plan])],
)
runner = Runner(agent, app=AppDeps(...))

handle = await runner.send(workspace, thread_id, "Draft a launch plan")
```

| Capability hook | What `ArtifactWorkspace` does |
|---|---|
| `get_toolset` | The generic tools: `list_artifacts`, `read_artifact`, `create_artifact`, `edit_text` (which can also propose), `archive_artifact`, and optionally `ask_user`. Their definitions never change, so the prompt cache stays warm. Application toolsets are registered on the agent itself ([ADR-0017](adr/0017-application-toolsets-and-capability-events.md)). |
| `get_instructions` | Renders, fresh from storage for every model request, the artifacts the thread follows, the kinds of artifact the agent can create, the thread's mode, and the agent's proposals awaiting review. |
| `wrap_run` | Records `run_started`, then briefs the agent: change notes since the thread's last-seen `seq` are enqueued before the first request. Watches the log for the run's duration (see below). When the run ends, records the agent's reply as `message_posted`, then `run_paused` with the deferred requests or `run_ended` with usage, storing the run's new `ModelMessage`s in the same transaction. A cancelled run is recorded as `stopped`, and one that raised as `failed`, with the `reason` of a `RunFailure` ([ADR-0042](adr/0042-typed-run-failures.md)). |
| `before_tool_execute`, `wrap_tool_execute`, `after_tool_execute` | Record every tool call and its result, the application's tools included, as `tool_called` and `tool_returned`: `ok`, `retry` (a rejection, or the tool's own `ModelRetry`) or `error` (`ToolFailed`, or an exception that fails the run). |
| `on_tool_execute_error` | Turns any `Rejection` into `ModelRetry` with the rejection's message (for a `VersionConflict`, adding "read the artifact again"), so tools never catch rejections themselves. Other exceptions are recorded and fail the run. |

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

`ctx.deps.workspace` acts as the agent (an `AgentActor` for this thread and run), so everything a tool commits is attributed to it. Reading, creating or editing an artifact through the generic tools also adds it to the thread's focus, so the agent hears about later changes to it.

Application tools emit ephemeral progress with `ctx.emit(...)`. `ArtifactDraft(kind=..., snapshot=...)` is a ready-made `CustomEvent` for a draft of an artifact being generated; other `CustomEvent`s reach live channels as `app_live` frames. Neither ever reaches the log.

### Change notes and steering

- When a run starts, the agent receives the notes it has missed, such as *"Alice changed plan_1 (plan, v7 → v8): completed Ship v1"*. They cover only the artifacts the thread follows (plus artifacts created in the thread), exclude the agent's own changes, and are delivered as a user-prompt part wrapped in `<workspace-changes>` tags, so they are stored in history with the rest of the conversation.
- The last-seen point is the `seq` at which the thread's history was last saved, so nothing is reported twice and nothing is skipped.
- While a run is in progress, a watcher subscribes to the log. Others' changes to followed artifacts are delivered the same way, and a new message in the thread is delivered as-is: a person can steer a long run without stopping it. Both use `ctx.enqueue(priority="asap")`, so they reach the model at its next request.

### Proposals and pausing

- Each artifact type declares a `write_policy`: `"direct"` or `"propose"`. A thread can be switched into suggest mode, which forces proposals for every type. `edit_text(..., propose=True)` proposes explicitly.
- Proposals do not block the run. The agent keeps working; the person accepts, rejects or edits the proposal whenever and from any surface; the outcome reaches the agent as a change note. When a proposal is accepted with edits, the note includes the person's changes.
- Blocking points use pydantic-ai's deferred tools: `ask_user` (or any tool raising `CallDeferred`) asks a question, and tools declared `requires_approval=True` need approval. The agent's `output_type` must include `DeferredToolRequests`. The run ends with `DeferredToolRequests`, recorded as `run_paused` with its history. Answers arrive as `answer_deferred` commands from any surface; once every request is answered, `Runner.resume` continues the run under the same `run_id` with `deferred_tool_results`. The pause survives restarts because nothing waits in memory.
- A chat message sent while a run is paused is the reply: it answers the pending questions and declines pending approvals with the message as the reason, and the run resumes. The conversation history therefore never ends in an unanswered tool call.

## Feedback

People's reactions and evaluators' verdicts are typed like artifacts ([ADR-0028](adr/0028-typed-feedback-as-events.md), [ADR-0037](adr/0037-feedback-targets-and-evaluators.md)). A feedback type is a Pydantic subclass of `Feedback`, registered by name, that declares the targets it can be given on:

```python
class Helpfulness(Feedback, name="helpfulness", targets={"turn", "thread"}):
    rating: Annotated[int, Field(ge=1, le=5)]
    reason: str | None = None
```

| Target | Identifies | Scope of its `feedback_given` |
|---|---|---|
| `ArtifactTarget(artifact_id, version)` | One version of an artifact | Workspace |
| `ThreadTarget(thread_id)` | A thread: the session | The thread |
| `TurnTarget(run_id)` | The agent's run, across its pauses | The run's thread |
| `MessageTarget(message_id, thread_id, run_id?)` | A message; `run_id` for the agent's, from its `message_posted` | The thread |

Feedback is the `give_feedback` command, so it goes through the one write path and every surface has it. Core checks the type is registered and declares the target's kind, validates the value, and checks the target exists, then records `feedback_given` with the validated value. An evaluator's verdict is an instance of the same types, given by an `EvaluatorActor(name, version)`, which may give feedback and nothing else; people's and evaluators' judgements can then be compared directly. Feedback is counted in `artifactr.feedback` by type, target and kind of actor.

**Scores.** Evaluation backends see feedback as scores, one per field, named `{type}.{field}` and typed by the field: numbers are numeric, `bool` boolean, `Literal` and `Enum` categorical, `str` text ([ADR-0038](adr/0038-feedback-as-scores.md)). The mapping and the ports are evalr's, shared with reflexr and with evalr's evaluators, so a person's scores and an evaluator's match by construction; `artifactr.scores` passes each type's registered name as the `{type}`. `artifactr.scores.FeedbackMirror` follows a workspace's log and records each `feedback_given`'s scores in a `ScoreSink`, attached to a trace or else a session:

| Target | Scored on |
|---|---|
| A turn | The trace of the run's latest attempt |
| A message | The latest trace of the run that posted it, when the target names it; else the thread's session |
| An artifact version | The trace the version was committed in; else the session of the agent that wrote it |
| A thread | The thread's session |

Score ids are derived from the envelope's id in artifactr's own namespace, so mirroring the log again replaces scores rather than adding more. A score has no evaluator; where the feedback came from (tenant, workspace, type, target, actor and `seq`) is its `source`, recorded as metadata. `sync_score_configs` creates each type's missing score configs in a `ScoreConfigStore`, through evalr's `sync_score_configs`. `ScoreSink` and `ScoreConfigStore` are evalr's ports: `artifactr.langfuse` adapts Langfuse to them, and passes evalr's contract suites for both. `artifactr.scores` re-exports evalr's `Score`, `ScoreConfig`, `ScoreSink`, `ScoreConfigStore`, `ScoreType` (as `ScoreDataType`) and `MAX_TEXT`, which it has always offered. It needs evalr, so it is used through the `langfuse` or `evals` extra; the inner layers never import it.

**Evaluation.** With the `[evals]` extra, feedback feeds evalr, the eval kit shared with reflexr ([ADR-0029](adr/0029-evalr-shared-eval-kit.md), [ADR-0044](adr/0044-the-evalr-adapter.md)):

- **Datasets:** `LogFeedbackSource` is evalr's `FeedbackSource` over a workspace's log. Each piece of one feedback type is an example: the feedback is its verdict, and the application builds its input from a `FeedbackContext`, the envelope plus the target's context. A target's context is read as of the target's end (a turn up to its run's last event, a message up to itself, an artifact version up to its change, a thread up to the feedback), with the thread's transcript, the run's events, the artifacts the thread followed then, and for an artifact version its revision. Evaluators' own verdicts are left out unless asked for.
- **Experiments:** `replay_task` is an evalr `Task` that seeds an isolated in-memory workspace with an example's thread (its followed artifacts, then its messages as the agent's history), sends the turn's message to a candidate agent through a `Runner`, and hands the turn's run, events, revisions and reply to an output builder.
- **Online evaluation:** `Runner(evaluators=[...])` takes `TurnEvaluator`s, a port. As each turn ends, inside its span, the `Runner` hands each one the turn, and a failure is recorded on the span, never raised. `OnlineEvaluator` adapts evalr's `OnlineEvaluation`: in the background, sampled and within a budget, it builds the input from the turn's context, has evalr judge it, and gives each verdict as feedback from `EvaluatorActor(name, version)`, so the mirror scores verdicts like people's feedback.
- **End-to-end measures:** `thread_sessions` and `artifact_histories` put the log into evalr's inputs, for drop-off and the rewrite rate. A version is written by whoever wrote its content: an accepted proposal is its proposer's, and one accepted with the reviewer's changes is the proposal and the person's rewrite at once. `TaskCompletion` is evalr's task-completion verdict as a feedback type, and `completion_transcript` builds a judge's input from a thread's transcript and final artifacts.

## The LLM gateway

Agents reach models through a LiteLLM proxy, which owns routing, budgets, rate limits and guardrails ([ADR-0031](adr/0031-litellm-proxy-first.md)). The `[litellm]` extra's `litellm_model` is a pydantic-ai model over the proxy, with default model settings like any other, and its `LiteLLMGateway` capability adds to each request, in `before_model_request`, the tenant, workspace, thread and run as LiteLLM metadata and tags, the thread as the session, the person as the user, the trace id and trace context, the workspace's guardrails from an application policy, and the tenant's virtual key from an application callback ([ADR-0043](adr/0043-the-litellm-adapter.md)). A request a guardrail blocks fails the run with the reason `guardrail_blocked` and is not retried ([ADR-0042](adr/0042-typed-run-failures.md)).

## Live output

The event log carries durable domain events only. Token-level output belongs to whoever drives the run ([ADR-0007](adr/0007-caller-owned-live-output.md)). pydantic-ai hands the run's event stream to its caller through `event_stream_handler`, and `forward_live(channel)` sends it to a `LiveChannel` as protocol live frames:

```python
await agent.run(
    prompt,
    deps=Session.start(workspace, thread_id, app=deps),
    message_history=await load_history(workspace, thread_id),
    event_stream_handler=forward_live(channel),  # caller-owned
)
```

The `Runner` does this for every run it starts, sending frames to its `FanoutChannel`, an in-process fan-out keyed by `run_id`. It keeps each active run's frames (bounded), so any connection can `runner.watch(run_id)` mid-run and receive what the run has produced so far, then the rest until it ends; watchers that fall behind lose their oldest frames rather than slowing the run. `NullChannel` drops frames for headless runs, and a pub/sub channel (Redis, NATS) can fan out across replicas.

The run holds a thread claim, not a socket: if the connection that started it drops, the run continues. Losing live frames is harmless, because the durable `message_posted`, `tool_returned` and `artifact_changed` events are authoritative. A client that reconnects mid-run replays the log from its last `seq` and watches the run again if it is still active.

## Tenancy and concurrency

- **Scoped handles.** `await workspaces.open(tenant_id, workspace_id, actor=...)` returns a `Workspace` bound to that tenant, workspace and actor. Nothing below it accepts a raw tenant id, so a query that crosses tenants cannot be written. Postgres row-level security can be layered underneath as defence in depth.
- **Actors are bound to handles.** `ws.as_actor(agent_actor)` returns a handle for the agent, and commits through it are attributed to the agent.
- **Type allowlist.** `Workspaces(storage, types=[Doc, Plan])` rejects creating any other artifact type, even one registered elsewhere in the process.
- **Optimistic concurrency.** Every edit names the version it was based on. A stale edit is rejected with the changes made since, so the agent retries against fresh state and a UI can rebase or ask the person.
- **One active run per thread**, enforced by `Workspace.claim_thread`: a storage lease with a time-to-live, renewed while held, that works across replicas and lapses if its holder dies. Concurrency happens across threads. A message sent during a run steers it instead of queueing.
- **Sequencing.** `seq` is assigned inside the commit transaction, which holds its workspace's lock from the moment it begins (in SQL, the workspace row, locked `FOR UPDATE`). The lock's holder advances the workspace's `head_seq`, giving a gap-free total order per workspace. This serializes commits within one workspace; tokens are not in the log, so commit volume stays modest.

## Surfaces

Every surface is a thin adapter: it authenticates, asks whether the client may use the workspace, turns its input into commands, and hands them to `Runner.execute`, through `Runner.execute_once` when the client gave a `command_id` ([ADR-0022](adr/0022-surfaces-over-one-command-handler.md)). Messages therefore start, steer or answer runs the same way everywhere, and every other command is a plain `Workspace.commit`. Authentication and authorization are the host's: the router takes `resolve_actor` and the MCP server `resolve`, and both take the same `authorize(tenant_id, workspace_id, actor)` hook (`artifactr.workspace.Authorize`), which the MCP server also asks before a resource read or subscription ([ADR-0012](adr/0012-surfaces-websocket-rest-mcp.md)).

| Surface | Package | Role |
|---|---|---|
| WebSocket | `artifactr.fastapi` | The thread protocol ([`protocol.md`](protocol.md)): `hello` and `welcome`, replay from a `seq` (or none, from the head of the log) then live events on one subscription, command frames and results, and live frames for runs in followed threads or on request. |
| REST | `artifactr.fastapi` | The same command frames at `POST .../commands`, and reads of artifacts, revisions, the log (a window of it, for some threads, from its start or its end), threads, proposals and runs. |
| MCP | `artifactr.mcp` | External agents join as `ExternalAgentActor`s: artifacts are resources at `artifactr://{tenant}/{workspace}/artifacts/{id}`, commands are tools that take an optional `command_id`, REST's reads (artifacts, revisions, the log, threads, proposals and runs) are tools too, and artifact changes become resource-updated notifications on the server's `SubscriptionBus`. |

```python
app = FastAPI(lifespan=lifespan)
app.include_router(artifactr_router(workspaces, runner, resolve_actor=resolve_actor), prefix="/v1")

mcp = ArtifactrMcp(workspaces, runner, resolve=resolve_client)
app.mount(
    "/mcp", mcp.http_app(streamable_http_path="/")
)  # run mcp.lifespan() in the app's lifespan
```

The WebSocket session reads with a single task and runs each command as its own task, so a `stop_run` is never stuck behind a slow command. All outgoing frames pass through one bounded outbox and one writer; a client too slow to keep up is disconnected (close code 4429) rather than holding events back, and resumes by `seq` when it reconnects. `Runner.execute_once` remembers each command's result in a `CommandResults` port, keyed by tenant, workspace, sender and `command_id`, so a retried command returns its original result on every surface. The default adapter, `InMemoryCommandResults`, keeps the 10,000 most recent per process.

The protocol's frames are Pydantic models in `artifactr.core.protocol`. `schemas/artifactr.v1.json` is generated from them (`make schema`) for clients to generate types from, and a test fails if it drifts.

pydantic-ai's AG-UI and Vercel AI adapters may be added later as compatibility surfaces for simple frontends. They are request-scoped with client-supplied state, so they sit beside the thread protocol rather than replacing it.

## Storage protocols

One protocol, `Storage`, covers everything a workspace persists ([ADR-0019](adr/0019-storage-protocol-and-workspace-handles.md)). Every method takes a `Scope` (tenant and workspace); `Workspace` handles hold the scope so application code never passes it.

```python
class Transaction(Protocol):
    async def load(self, needs: Needs) -> State: ...
    async def save(
        self, result: CommitResult, *, actor: Actor
    ) -> list[Envelope]: ...  # assigns seq
    async def append_history(self, thread_id: ThreadId, messages: bytes) -> None: ...


class Storage(Protocol):
    def transaction(self, scope: Scope) -> AbstractAsyncContextManager[Transaction]: ...
    async def read(
        self,
        scope: Scope,
        *,
        after_seq: int = 0,
        before_seq: int | None = None,
        threads: Collection[ThreadId] | None = None,
        limit: int | None = None,
        last: int | None = None,
    ) -> list[Envelope]: ...
    def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncIterator[Envelope]: ...
    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool: ...

    # plus reads: artifact(s), revisions, thread(s), proposal(s), run, head_seq, history
```

- **Transactions serialize per workspace from the moment they begin**, so what a transaction loads cannot change before it saves. Writes are staged and applied atomically when the block exits normally; an exception rolls back entities, log and history together.
- **`read` takes a window of the log** (`after_seq < seq < before_seq`), for some threads by `delivered_to`'s rule, and its first `limit` or last `last` envelopes, oldest first. Storage filters, so a tail read of a long log reads only its tail; `Workspace.read` refuses both `limit` and `last`.
- **`subscribe(after_seq)` replays, then follows live**, on one iterator. Because a subscription starts from a `seq`, there is no gap to manage between history and live events. It is the only read path for replay, live fan-out, hooks, MCP notifications and change notes.
- **Leases** back `Workspace.claim_thread`: a time-limited, renewed claim that holds across processes and lapses if its holder dies.
- **History** is opaque bytes (pydantic-ai `ModelMessage`s serialized by the agent layer), appended in the same transaction as the run fact that ends each run segment.

Two implementations ship:

- **`InMemoryStorage`** (`artifactr.workspace`), for tests, examples and single-process prototypes. A per-workspace `asyncio.Lock` serializes transactions and an `asyncio.Condition` wakes subscribers. Its clock is injectable, so tests control lease expiry.
- **`SqlStorage`** (`artifactr.sql`), for production: SQLAlchemy 2 async, with the same code on PostgreSQL and SQLite ([ADR-0021](adr/0021-sql-storage.md)). A SQLite engine keeps one connection, so a process's transactions take turns in order.

```python
engine = create_async_engine("postgresql+asyncpg://localhost/app")  # artifactr-ai[postgres]
await migrate(engine)  # the packaged Alembic migrations, up to the latest
workspaces = Workspaces(SqlStorage(engine))
```

`SqlStorage` works like this:

- **Locking.** A transaction creates its workspace's row if the workspace is new, then locks it (`SELECT ... FOR UPDATE`) before it loads anything. `save` assigns `seq` from the row's `head_seq`. PostgreSQL runs at its default `READ COMMITTED` isolation. SQLite has no row locks, so engines from `create_sqlite_engine` begin every transaction with `BEGIN IMMEDIATE`, which takes the database's write lock instead.
- **Tables.** Every primary key starts with the tenant and the workspace, and every table name with `artifactr_`. Entities are stored as the JSON of their Pydantic models, beside the columns that reads filter on (kind, archived, status, thread, and each event's type and thread). Lists come back oldest first, by a creation position counted on the workspace row.
- **Subscriptions** read the log a page at a time. Once caught up, they wait for a commit through the same `SqlStorage`, which wakes them at once, or poll every `poll_interval` (0.5 s by default) for commits from other processes.
- **Leases** are rows, taken with a conditional update or an insert, so two processes racing for a lease cannot both win.
- **Migrations** ship in the package and record their version in `artifactr_alembic_version`, apart from the application's own. `migrate(engine)` upgrades a database; `create_schema(engine)` creates the tables without migrations, for tests and prototypes. A test checks that the migrations build exactly the models' schema.

The workspace behaviour suite in `tests/workspace/` runs against every implementation: in memory, on SQLite, and on PostgreSQL.

## Observability

artifactr is traced and measured through the OpenTelemetry API only, under the instrumentation scope `artifactr` at the package version ([ADR-0027](adr/0027-opentelemetry-observability-with-langfuse.md)). It never configures the SDK, never calls `Agent.instrument_all()`, and never creates a backend client; with no SDK configured, recording is a no-op. `Workspaces`, `Runner` and `artifactr_router` take an optional `tracer_provider` and `meter_provider`, defaulting to the global ones. The [observability guide](guides/observability.md) shows how an application turns it on.

### Spans

| Span | Name | Key attributes |
|---|---|---|
| A turn: the `Runner` handling a message, or answers that resume a run | `invoke_workflow turn`, a new trace linked to the span that started it ([ADR-0035](adr/0035-a-turn-is-its-own-trace.md)) | `gen_ai.operation.name=invoke_workflow`, `gen_ai.workflow.name=turn`, `artifactr.turn.trigger`, `artifactr.turn.outcome`, `langfuse.observation.type=chain` |
| A command committed through `Workspace.commit` | `artifactr.commit {type}` | `artifactr.command.type`, `artifactr.outcome`, `artifactr.rejection`, and what the command is about: `artifactr.artifact.id`, `artifactr.artifact.version`, `artifactr.proposal.id`, `artifactr.patch.kind`, `artifactr.patch.size` |
| The agent run inside a turn | pydantic-ai's `invoke_agent` | artifactr's attribution, added by the capability's `wrap_run` |
| A tool call | pydantic-ai's `execute_tool` | artifactr's attribution, and `artifactr.artifact.id` when the tool is about one artifact |
| A WebSocket connection | `artifactr.stream` | `artifactr.stream.close_code` |
| A REST request | FastAPI's own, when the application instruments FastAPI | artifactr's attribution |
| An MCP request | The MCP SDK's own | artifactr's attribution |

Every span artifactr owns or wraps is attributed: `artifactr.tenant.id`, `artifactr.workspace.id` and `artifactr.actor.kind`; with a thread, `session.id`, `gen_ai.conversation.id` and `artifactr.thread.id` set to the thread id, which is the session; with a run, `artifactr.run.id`; and for a person, `user.id`. The `Runner` passes the thread as pydantic-ai's `conversation_id`, and never passes artifactr's run id as pydantic-ai's `run_id`: an artifactr run spans pauses, and each attempt is a separate pydantic-ai run. artifactr's own spans carry ids, kinds, versions and counts, never content; prompts and messages are on pydantic-ai's spans when its `include_content` is on.

Each attempt's trace id is recorded with `run_started`, and each revision records the trace it was committed in ([ADR-0033](adr/0033-trace-links-on-runs-and-revisions.md)).

### Metrics

The metric registry, `artifactr.telemetry.metrics`, declares every metric with its instrument, unit, description and allowed attributes. artifactr records only declared attributes. Commands are counted by `Workspace.commit`, turns by the `Runner`, connections by the stream, and everything else from the events each commit or fact appends, so every surface is counted the same way.

| Metric | Instrument | Attributes, besides tenant and workspace |
|---|---|---|
| `artifactr.commands` | counter | `artifactr.command.type`, `artifactr.outcome`, `artifactr.rejection`, `artifactr.actor.kind` |
| `artifactr.commit.duration` | histogram, s | `artifactr.command.type`, `artifactr.outcome` |
| `artifactr.turns`, `artifactr.turn.duration` | counter; histogram, s | `artifactr.turn.trigger`, `artifactr.turn.outcome` |
| `artifactr.runs` | counter | `artifactr.run.status` and `artifactr.run.reason`, for each segment that ends or pauses |
| `artifactr.tool_calls` | counter | `gen_ai.tool.name`, `artifactr.tool.status` |
| `artifactr.tokens` | counter | `gen_ai.token.type` |
| `artifactr.messages` | counter | `artifactr.actor.kind` |
| `artifactr.artifact.changes` | counter | `artifactr.artifact.kind`, `artifactr.change`, `artifactr.actor.kind` |
| `artifactr.proposals` | counter | `artifactr.proposal.action`, `artifactr.actor.kind` |
| `artifactr.feedback` | counter | `artifactr.feedback.type`, `artifactr.feedback.target`, `artifactr.actor.kind` |
| `artifactr.stream.connections` | up-down counter | |
| `artifactr.stream.disconnects` | counter | `artifactr.stream.close_code` |

pydantic-ai adds `gen_ai.client.token.usage` and `operation.cost` per model request, by model; the registry lists them, and the instrumentations' HTTP and database metrics, as external metrics the dashboards may read.

**Cardinality.** Thread, turn, run, artifact and message ids are never metric attributes; those granularities come from traces. Tenant and workspace are attributes by default. `metrics_detail="workspace" | "tenant" | "none"` limits them, applied by OpenTelemetry views before aggregation (`artifactr.otel.metric_views`) rather than by the library ([ADR-0036](adr/0036-metric-cardinality-through-sdk-views.md)).

### Dashboards

Grafana dashboards live in `deploy/grafana/dashboards/`, generated by `scripts/grafana_dashboards.py`:

| Dashboard | What it shows |
|---|---|
| Overview | Every tenant: commands, rejections, turns and their latency, connections, tokens |
| Tenant | One tenant's busiest workspaces, tokens, messages and turn latency |
| Workspace | One workspace's commands, rejections, artifact changes, turns, tool calls and feedback |
| Agent and LLM | Tokens and cost by model, time to first chunk, run outcomes, tool failure and retry rates |
| Collaboration | Proposals and their acceptance, who edits artifacts, the agent's share of edits, feedback |
| Surfaces | REST and MCP traffic and latency, WebSocket connections and close codes, commands by kind of actor |
| Storage | Commit latency, version conflicts, failed commits and the database pool |

They read Prometheus through the data source uid `prometheus`, as stackr provisions it, and a test checks that every query reads a metric in the registry, with labels its attributes declare ([ADR-0041](adr/0041-dashboards-generated-tested-and-released.md)). Every query has a one-minute min step, so rates span several of the OpenTelemetry SDK's minutely exports, and the `$job` variable's "All" is the services that record artifactr's metrics, since other services share the external metrics' names. Each release attaches them as assets, one by one and as `artifactr-dashboards-<version>.tar.gz`, the archive stackr downloads to provision them by version.

### Configuring the SDK

The `[otel]` extra's `configure_telemetry(...)` is for applications and the reference implementation; no part of the library requires it. It sets up the tracer, meter and logger providers with the service's resource, OTLP over HTTP, the metric views, a `BaggageSpanProcessor` that copies a turn's `session.id` onto every span in it (database and HTTP spans included), the open instrumentations for FastAPI, SQLAlchemy, asyncpg, httpx and httpx2, and pydantic-ai's `InstrumentationSettings`. It returns a handle that instruments FastAPI apps and SQLAlchemy engines created later, gives agents pydantic-ai's `Instrumentation` capability, and shuts everything down.

The `Runner` takes a `turn_context`: an async context entered around each turn, inside its span, given the run's session. It is a port for backends that attribute a turn in their own way, such as Langfuse's propagated trace attributes. Its `evaluators` are another port, for judging turns after they end (see [Feedback](#feedback)).

### Langfuse

Langfuse is the primary backend for traces and scores ([ADR-0027](adr/0027-opentelemetry-observability-with-langfuse.md), [ADR-0039](adr/0039-the-langfuse-adapter.md)). The `[langfuse]` extra adds `should_export_span`, a filter that keeps artifactr's, pydantic-graph's, the MCP SDK's and the HTTP and database instrumentations' spans as well as Langfuse's default LLM spans, so traces stay whole; `langfuse_turn`, a `TurnContext` that propagates each turn's session, user, tags (tenant, workspace, the kinds of artifact followed), trace name and metadata; and `LangfuseScores` and `LangfuseScoreConfigs`, which put feedback in Langfuse through evalr's score ports, sending a yes or no as 1 or 0. `configure_telemetry(langfuse=True)` adds Langfuse to the same tracer provider. A Collector can also send plain OTLP to Langfuse's HTTP endpoint, with the `x-langfuse-ingestion-version: 4` header.

## Dependencies

| Dependency | Used for | Current major (2026-09) |
|---|---|---|
| pydantic | Artifact types, commands, events, JSON Schema | 2.13 |
| jsonpatch | RFC 6902 apply and diff in core | 1.33 |
| pydantic-ai-slim | Agent runtime: capabilities, toolsets, deferred tools, message history | 2.51 |
| SQLAlchemy (asyncio) | SQL storage | 2.1 |
| Alembic | SQL migrations | 1.20 |
| asyncpg, aiosqlite | PostgreSQL and SQLite drivers (extras; the library imports neither) | 0.31, 0.22 |
| FastAPI | WebSocket and REST adapter | 0.141 |
| mcp | MCP server (`MCPServer`, subscriptions) | 2.2 |
| langfuse (extra) | Traces, scores and score configs in Langfuse | 4.15 |
| evalr (extras) | Evaluators, datasets, experiments, online evaluation and end-to-end measures (`evals`); the score mapping and ports (`langfuse`, `evals`); pinned by revision until published | 0.1 |
| opentelemetry-api | Spans and metrics, through the API only | 1.45 |

Python 3.12+. Tooling: uv, ruff, pyright in strict mode, pytest, and Zensical with mkdocstrings for the documentation site ([ADR-0023](adr/0023-documentation-site.md)).

## Testing

- **Core:** conformance fixtures, plus property tests (hypothesis) that patches round-trip: applying `diff(a, b)` to `a` gives `b`.
- **Workspace:** one suite runs against in-memory storage, SQLite and PostgreSQL. SQLite alone reaches the coverage gate; PostgreSQL runs when `ARTIFACTR_TEST_POSTGRES_URL` is set, and always in CI.
- **SQL:** concurrent transactions, lease races and cross-process subscriptions on both databases, and a check that the migrations build exactly the models' schema.
- **Agent:** scripted runs with pydantic-ai's `TestModel`, and `FunctionModel`s built by `function_model`, which streams as the `Runner` needs, so no test calls a model API. Assertions are on the events written, including conflicts, steering and deferred pauses.
- **Adapters:** WebSocket contract tests with FastAPI's `TestClient`, and an MCP client round-trip.
- **Evaluation:** the feedback source passes evalr's `check_feedback_source` contract, and the Langfuse score adapters its `check_score_sink` and `check_score_config_store`; experiments run through evalr's in-memory tracker, and evaluators are evalr's `FunctionEvaluator`s.
- **Telemetry:** spans and metrics are asserted through the OpenTelemetry SDK's `InMemorySpanExporter` and `InMemoryMetricReader`, and the registry's cardinality policy is checked for every metric.
- **Protocol:** the JSON Schema in `schemas/` is generated from the models and checked in. CI fails if it drifts.

The contributor stack is `compose.yaml`: PostgreSQL for the tests, and docplan under the `app` profile. The dev container is built on it and joins stackr's network when stackr's stack runs ([ADR-0030](adr/0030-compose-and-dev-containers.md), [ADR-0040](adr/0040-joining-stackrs-network.md)). CI validates the Compose files without starting containers.

## Build plan

The phases, their exit criteria and their progress are tracked in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md) for v0.1, and in [RFC-0002](rfcs/0002-observability-feedback-and-evaluation.md) for observability, feedback, evaluation and the LLM gateway.

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
| [0019](adr/0019-storage-protocol-and-workspace-handles.md) | One storage protocol behind workspace handles |
| [0020](adr/0020-running-agents-in-threads.md) | Running agents in threads |
| [0021](adr/0021-sql-storage.md) | SQL storage with one dialect-neutral implementation |
| [0022](adr/0022-surfaces-over-one-command-handler.md) | Surfaces over one command handler |
| [0023](adr/0023-documentation-site.md) | The documentation site |
| [0024](adr/0024-reference-implementation-as-a-workspace-member.md) | The reference implementation as a workspace member |
| [0025](adr/0025-distribution-name.md) | Distributed as artifactr-ai, imported as artifactr |
| [0026](adr/0026-publishing-the-documentation-site.md) | Publishing the documentation site from main |
| [0027](adr/0027-opentelemetry-observability-with-langfuse.md) | OpenTelemetry-native observability, with Langfuse primary |
| [0028](adr/0028-typed-feedback-as-events.md) | Typed feedback as events, mirrored to Langfuse |
| [0029](adr/0029-evalr-shared-eval-kit.md) | evalr, a shared eval kit |
| [0030](adr/0030-compose-and-dev-containers.md) | Contributor Compose and dev containers here, infrastructure in stackr |
| [0031](adr/0031-litellm-proxy-first.md) | LiteLLM, proxy first, for routing and guardrails |
| [0032](adr/0032-libraries-and-the-stackr-template.md) | Libraries, and stackr as the infrastructure template |
| [0033](adr/0033-trace-links-on-runs-and-revisions.md) | Trace links on runs and revisions |
| [0034](adr/0034-ports-and-adapters-for-integrations.md) | Ports and adapters for integrations |
| [0035](adr/0035-a-turn-is-its-own-trace.md) | A turn is its own trace |
| [0036](adr/0036-metric-cardinality-through-sdk-views.md) | Metric cardinality through SDK views |
| [0037](adr/0037-feedback-targets-and-evaluators.md) | Feedback targets and evaluators |
| [0038](adr/0038-feedback-as-scores.md) | Feedback as scores, through ports |
| [0039](adr/0039-the-langfuse-adapter.md) | The Langfuse adapter |
| [0040](adr/0040-joining-stackrs-network.md) | Joining stackr's network when it runs |
| [0041](adr/0041-dashboards-generated-tested-and-released.md) | Dashboards generated, tested and released |
| [0042](adr/0042-typed-run-failures.md) | Typed run failures |
| [0043](adr/0043-the-litellm-adapter.md) | The LiteLLM adapter |
| [0044](adr/0044-the-evalr-adapter.md) | The evalr adapter |

## Open questions

- **Log retention.** When old envelopes are compacted, `resume` falls back to a snapshot. The snapshot format is not yet specified.
- **Very hot workspaces.** Assigning `seq` serializes commits per workspace. If that becomes a bottleneck, the log could be sharded by artifact group behind the same per-workspace cursor.
- **Change-note volume.** With many concurrent chats, notes may need coalescing beyond focus filtering.
- **Crash recovery for runs.** A run interrupted by a process crash is recorded as failed when its lease expires. pydantic-ai's durable execution integrations (Temporal, DBOS, Prefect) could make such runs resumable.
- **Pushing log updates across processes.** `SqlStorage` subscriptions learn about commits from other processes by polling. PostgreSQL's `LISTEN/NOTIFY` could wake them at once: an optimisation behind the same `subscribe`, with polling kept for SQLite and as a fallback ([ADR-0021](adr/0021-sql-storage.md)).
- **Cross-process runs.** Runs are tasks in the process that started them, so `Runner.stop` and `Runner.watch` reach only local runs. A pub/sub channel would make both work across replicas.
- **Cross-process deduplication.** `InMemoryCommandResults` remembers results in one process, and a retry that arrives while the first attempt is still being carried out runs again. A `CommandResults` over shared storage, with a claim on a command while it runs, would close both gaps ([ADR-0022](adr/0022-surfaces-over-one-command-handler.md)).
- **`jsonpatch` maintenance.** It is stable but rarely updated; its surface is small enough to vendor if needed.
- **The session on database and HTTP spans in a real deployment.** A `BaggageSpanProcessor` carries a turn's `session.id` onto every span in it, as a test shows in process ([ADR-0035](adr/0035-a-turn-is-its-own-trace.md)). Whether a deployed Collector and Langfuse keep it end to end is left for stackr's integration tests.
- **Guardrail error shapes.** A guardrail block is recognised as an HTTP 400 whose error mentions a guardrail ([ADR-0043](adr/0043-the-litellm-adapter.md)). If LiteLLM adds a typed error code for blocks, the gateway should use it.
- **Mirroring many workspaces.** A `FeedbackMirror` follows one workspace. Applications with many start one per active workspace; a shared follower across a tenant's workspaces would need a storage-level subscription.
