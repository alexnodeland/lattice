# ADR-0008: Agent perception: change notes, fresh rendering, steering

**Status:** Accepted; its steering amended by [ADR-0055](0055-turns-from-the-log.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Shared artifacts are only a second channel of communication if the agent notices what others did in them. If people's edits are silent, or if the agent works from a copy cached for the life of a connection, it acts on stale state, or on its own earlier proposal instead of what the person actually accepted.

People also need to redirect a long-running agent without stopping it.

## Decision

- **Every change is attributed.** Each change produces an `artifact_changed` event carrying its actor ([ADR-0002](0002-single-write-path.md)).
- **Notes at run start.** `core.change_notes` turns the log since the thread's last-seen `seq` into short notes, which go into the prompt and are therefore persisted in the run's `ModelMessage`s. Notes cover only artifacts the thread is focused on, and they exclude the agent's own changes.
- **Notes during a run.** The capability subscribes to the log for the run's duration. Other actors' changes to focused artifacts are delivered into the live run with `ctx.enqueue(priority="asap")` and reach the model at its next request.
- **Fresh rendering.** Focused artifacts are rendered from storage by `get_instructions`, never cached across runs or connections. Available actions are listed as text, so tool definitions stay constant and the prompt cache stays warm.
- **Steering.** One run is active per thread. A message posted during a run is delivered into it through the same enqueue path, instead of queueing as a new turn.

## Options considered

### Option A: Change notes, fresh rendering and steering (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Agent awareness | High: knows what changed and who changed it |
| Prompt-cache friendliness | High |

**Pros:** the agent reasons about others' edits explicitly; people can redirect it mid-run.
**Cons:** note volume needs filtering; the model must handle interruptions gracefully.

### Option B: Fresh rendering only

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Agent awareness | Partial: sees current state, not what changed |
| Prompt-cache friendliness | Medium |

**Pros:** simple.
**Cons:** the agent cannot tell what changed or who changed it.

### Option C: A reactive agent (edits wake the agent unprompted)

| Dimension | Assessment |
|---|---|
| Complexity | High |
| Agent awareness | Highest |
| Prompt-cache friendliness | Medium |

**Pros:** proactive collaboration.
**Cons:** unrequested runs cost money and can be noisy; better built on top of Option A later.

For messages sent mid-run, queueing them as the next turn and rejecting them while busy were also considered. Both force a person to wait out or stop a run they only want to adjust.

## Trade-off analysis

Option A delivers what the product promises, mutual awareness, using two pydantic-ai primitives (instructions and enqueue) plus one pure function in core. Option C can be built later as an application policy over the same log subscription.

## Consequences

- Easier: the agent's view of the workspace is always current and attributed.
- Harder: instructions must tell the model that notes and messages may arrive mid-run.
- Revisit note coalescing when many chats edit the same artifacts.

## Action items

1. [ ] Implement `core.change_notes` with focus filtering and coalescing.
2. [ ] Implement the run subscription and enqueue path in `ArtifactWorkspace.for_run`.
3. [ ] Test steering with `FunctionModel`.
