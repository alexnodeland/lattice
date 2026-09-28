# ADR-0020: Running agents in threads

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Building the agent layer (RFC-0001 phase 3) raised questions the earlier ADRs left open:

- How change notes enter the model's context.
- How the agent's "last seen" point is tracked.
- What a message does when the thread's run is running, idle, or paused on a question.
- How surfaces start, stop and watch runs without each reimplementing it.

Two spikes against pydantic-ai 2.51 also established facts the design relies on:

- Content enqueued in `wrap_run` before the first request arrives right after the user's prompt.
- Raising `ModelRetry` from `on_tool_execute_error` makes the model redo the call.
- Resuming with `DeferredToolResults` executes approved calls.
- `CustomEvent` reserves the field name `data`.
- pydantic-ai recognizes a tool's context only from a literal `RunContext[...]` annotation.

A new problem appeared as well: if a person replies in the chat while a run is paused on a question, starting a fresh run would leave the model history ending in an unanswered tool call, which model APIs reject.

## Decision

- **Change notes are user-prompt parts wrapped in `<workspace-changes>` tags**, enqueued before the first request and during the run. They are stored in history like the rest of the conversation. A system-prompt part was rejected because some providers hoist mid-conversation system text out of position.
- **Last seen is the `seq` of the thread's last saved history.** Storage records each history chunk with the log's head at the moment it commits, so the next run is briefed on exactly what happened since.
- **`wrap_run` owns the run's record.** It records `run_started` and the briefing, runs a log watcher for the run's duration, and ends with exactly one of `run_paused`, `run_ended(completed)`, `run_ended(stopped)` or `run_ended(failed)`. The tool-execution hooks record every tool call, including the application's. Any `Rejection` becomes a `ModelRetry` carrying its message.
- **A `Runner` gives a message one meaning everywhere:**
  - in an idle thread it starts a run
  - in a busy thread it steers the running agent, which the watcher delivers
  - in a thread whose run is paused, it is the reply: it answers pending questions and declines pending approvals with the message as the reason, then resumes the run
- **The `Runner` also provides:**
  - `answer`, which resumes the run once every request is answered
  - `stop`, which cancels a run in this process
  - `watch`, a run's live frames from its `FanoutChannel`
- **Runs are asyncio tasks in the process that started them.** Their thread claim holds across processes, but `stop` and `watch` only reach local runs. Cross-process stop and fan-out need a pub/sub channel, deferred beyond v0.1.
- **`ArtifactDraft(kind, snapshot, artifact_id)`** is a ready-made `CustomEvent` that application tools emit for drafts. Its field is `snapshot` because `CustomEvent` reserves `data`.
- **Following is automatic:** reading, creating or editing an artifact through the generic tools adds it to the thread's focus.

## Options considered

### What a message does while a run is paused

| Option | History stays valid | Natural for people |
|---|---|---|
| **Treat it as the reply (chosen)** | Yes | Yes: people answer in the chat |
| Start a new run beside the paused one | No: dangling tool calls | Yes |
| Reject the message until the pause is answered | Yes | No |

### Where orchestration lives

| Option | Duplication across surfaces | Testable without a transport |
|---|---|---|
| **A `Runner` in the agent layer (chosen)** | None | Yes |
| Each adapter drives `agent.run` itself | High | No |

## Consequences

- Easier: WebSocket, REST and MCP adapters call `runner.send`, `answer`, `stop` and `watch`; none of them implements run logic.
- Easier: the whole agent layer is tested with scripted models, with no network and no transport.
- Harder: stopping or watching a run started by another process needs a shared channel (future work, listed in the architecture's open questions).
- A chat reply to a paused run cannot be told apart from an unrelated message. That is acceptable, because the agent sees the text either way.

## Action items

1. [x] Implement `Session`, `ArtifactWorkspace`, the generic tools, live forwarding and `Runner` (RFC-0001 phase 3).
2. [x] Use the `Runner` from the WebSocket, REST and MCP adapters (phase 5, [ADR-0022](0022-surfaces-over-one-command-handler.md)).
3. [ ] A pub/sub live channel and cross-process stop (after v0.1).
