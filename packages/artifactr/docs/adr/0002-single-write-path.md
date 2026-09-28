# ADR-0002: One write path: commands through `Workspace.commit`

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Artifacts are changed by many actors: the built-in agent's tools, people through a UI over WebSocket or REST, external agents over MCP, and scripts. When each surface implements its own write logic, validation, merging and notification drift apart. Some writes end up silent, visible neither to other participants nor to the agent, which undermines the point of a shared workspace.

An earlier iteration of this design had tools return their effects as values for the framework to commit after the tool returned. That breaks down on conflicts: by the time the commit fails, the tool has already told the model it succeeded.

## Decision

Every change is a **command** submitted through `Workspace.commit(command)`:

1. Open a host transaction and load the current state.
2. Call `core.commit(command, current, actor)`, which either returns a `CommitResult` or raises a typed rejection.
3. Save the revisions, assign `seq`, append the events, and commit.
4. Return `Applied` or `Proposed` to the caller, or raise the rejection.

Nothing else writes artifacts or events. Run lifecycle facts (a run started, a tool was called) are recorded through `Workspace.record`, which uses the same transaction and sequencing. Agent tools call `commit` directly and see the outcome, so a `VersionConflict` reaches the model as a retry.

## Options considered

### Option A: Commands through one `Workspace.commit` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Consistency across surfaces | Guaranteed: one code path |
| Conflict feedback to the agent | Direct: the tool sees the rejection |

**Pros:** surfaces are thin adapters; every change is attributed and published; one place to test.
**Cons:** the `Workspace` API must stay small and stable, because everything depends on it.

### Option B: Effects returned as values, committed after the tool returns

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Consistency across surfaces | Good for tools; other surfaces need their own path |
| Conflict feedback to the agent | Broken: the tool has already returned success |

**Pros:** tools cannot write outside the pipeline.
**Cons:** conflicts need extra machinery to retract a tool result; a second path is still needed for non-agent actors.

### Option C: Each surface calls repositories directly

| Dimension | Assessment |
|---|---|
| Complexity | Low at first, high over time |
| Consistency across surfaces | Poor: logic is duplicated |
| Conflict feedback to the agent | Depends on each implementation |

**Pros:** familiar layering.
**Cons:** duplicated accept, merge and validation logic that drifts; silent writes.

## Trade-off analysis

Option B's appeal was that tools could not bypass the pipeline. Option A keeps that property, because tools can only reach storage through the `Workspace`, and it also lets the tool see the outcome. Option C is the default shape for many backends, and it is where duplicated write logic comes from.

## Consequences

- Easier: adding a surface means translating its input into commands.
- Easier: every change produces the same events and change notes, whoever made it.
- Harder: operations that need several changes at once need a composite command, or a transaction spanning several commits, rather than ad hoc writes.
- Revisit if a use case needs writes that are not expressible as commands.

## Action items

1. [ ] Define the closed `Command` union and the `CommitResult`, `Applied` and `Proposed` types in core.
2. [ ] Implement `Workspace.commit` and `Workspace.record` over the storage protocol.
3. [ ] Add conformance fixtures for every command.
