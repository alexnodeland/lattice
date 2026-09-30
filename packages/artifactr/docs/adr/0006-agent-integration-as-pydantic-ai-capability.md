# ADR-0006: Agent integration as a pydantic-ai capability

**Status:** Accepted, amended by [ADR-0017](0017-application-toolsets-and-capability-events.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

pydantic-ai 2.x provides the machinery an artifact-aware agent needs:

- **Capabilities**, which bundle toolsets and instructions and hook into every stage of a run: the run itself, each model request, tool validation and execution, and the event stream.
- `RunContext.emit` for typed `CustomEvent`s.
- `RunContext.enqueue` for delivering messages into a run in progress.
- Deferred tools for pausing.
- `ModelMessagesTypeAdapter` for storing history.

A custom runner around the agent would reimplement these, and it would not compose with other capabilities an application uses, such as instrumentation or content filters.

## Decision

`artifactr.agent` provides one capability, `ArtifactWorkspace(AbstractCapability[Session])`:

- `get_toolset` contributes generic artifact tools plus the application's toolsets.
- `get_instructions` renders focused artifacts and the currently available actions.
- `before_run`, `for_run`, `on_event`, `on_tool_execute_error`, `after_run` and `on_run_error` record run lifecycle events, deliver change notes and steering messages, and turn `VersionConflict` into `ModelRetry`.

A turn is a plain `agent.run(...)`. Tools are plain pydantic-ai tools over `RunContext[Session]`. `Session` is the run's deps: a workspace handle bound to the agent's actor, the thread, the run id, the focus set, the last-seen `seq`, and the application's own deps (`Session[AppDeps]`). Model history is stored as `ModelMessage`s. Core never imports pydantic-ai.

## Options considered

### Option A: One capability (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: pydantic-ai does the orchestration |
| Composability | High: combines with any other capability |
| Coupling to pydantic-ai | High, confined to one package |

**Pros:** idiomatic; the agent is built once; improvements in pydantic-ai arrive for free.
**Cons:** tracks a fast-moving dependency.

### Option B: A custom runner around `agent.iter`

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Composability | Low |
| Coupling to pydantic-ai | High, spread through the runner |

**Pros:** full control over every step.
**Cons:** reimplements hooks, event bridging and history handling; very large turn functions are the usual result.

### Option C: A custom tool context and effect sink wrapping each tool

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Composability | Low: tools depend on artifactr types |
| Coupling to pydantic-ai | Medium |

**Pros:** explicit control of tool effects.
**Cons:** duplicates `RunContext.emit` and capability hooks.

## Trade-off analysis

Everything Option B would build (lifecycle hooks, an event bridge, per-run state) exists as capability hooks with defined ordering. Choosing the capability means accepting pydantic-ai's churn, but that churn is confined to `artifactr.agent`; `core` and `workspace` do not depend on it.

## Consequences

- Easier: applications add artifactr to an existing agent with one line.
- Easier: application tools are ordinary pydantic-ai tools.
- Harder: upgrades of pydantic-ai's major version need attention; pin the major and track its changelog.
- Revisit if a needed hook point is missing from the capability API.

## Action items

1. [ ] Implement `Session[AppDeps]` and `ArtifactWorkspace`.
2. [ ] Implement generic tools: list, read, edit document text, propose.
3. [ ] Test with `TestModel` and `FunctionModel`, asserting the events written.
