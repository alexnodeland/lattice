# ADR-0010: Pausing with pydantic-ai deferred tools

**Status:** Accepted; its answers amended by [ADR-0073](0073-checks-that-refuse-a-command-before-it-commits.md), the amendment below, and [ADR-0084](0083-ask-user-asks-questions-with-options.md), `ask_user`'s questions and answers
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Some tools need a person before the run can continue: a question the agent needs answered, or an action that requires approval. Waiting on an in-memory future is lost on restart and does not work across processes. Offering both an in-memory future and a durable fallback means two mechanisms that must agree on the same behaviour.

pydantic-ai provides deferred tools. A tool raises `CallDeferred` or `ApprovalRequired` (or is declared as requiring approval). The run then ends with `DeferredToolRequests` and is resumed later with `deferred_tool_results`.

## Decision

Use pydantic-ai's deferred tools as the only pause mechanism:

1. The run ends with `DeferredToolRequests`. The capability records `run_paused` with the pending requests, and the run's `ModelMessage`s are stored.
2. An `answer` command from any surface records each answer or approval.
3. When every request is answered, the host resumes with `agent.run(message_history=..., deferred_tool_results=DeferredToolResults(...))` under the same artifactr `run_id`.

Clients see one run that spans the pause.

## Options considered

### Option A: Deferred tools only (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one mechanism |
| Durability | Survives restarts and works across replicas |
| Latency | A resume re-sends history (mitigated by prompt caching) |

**Pros:** one path; nothing waits in memory; answers can come from any surface at any time.
**Cons:** each pause ends the underlying model run.

### Option B: An in-memory future, falling back to deferred tools

| Dimension | Assessment |
|---|---|
| Complexity | Medium: two paths |
| Durability | Durable only on the fallback path |
| Latency | Lowest while connected |

**Pros:** feels synchronous.
**Cons:** two mechanisms with the same semantics to keep aligned.

### Option C: An in-memory future only

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Durability | None |
| Latency | Lowest |

**Pros:** simplest.
**Cons:** lost on restart; breaks with more than one process.

## Trade-off analysis

Option A trades a little latency on resume for durability and a single code path. Since the artifactr `run_id` spans the pause, the break is invisible to clients. A fast path can be added later if measured latency justifies it.

## Consequences

- Easier: pauses survive deploys; answers can arrive from REST, WebSocket or MCP.
- Harder: tools that pause must be written for resumption (idempotent up to the pause point).
- Revisit if resume latency is measured to hurt the experience.

## Action items

1. [ ] Record `run_paused` from `DeferredToolRequests` in the capability.
2. [ ] Implement the `answer` command and resumption in the workspace and adapters.
3. [ ] Test a pause and resume across a simulated restart.

## Amendment (2026-10-17): an answer names its tool, and may be refused

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) adds forms, which a run asks with `ask_form`, a deferred tool of `artifactr.ui`'s ([ADR-0074](0074-forms-and-dashboards-in-artifactr-ui-behind-the-forms-extra.md)) whose answer is the form's values.

- **An answer names its tool.** `deferred_answered` carries `tool_name`, copied from the request by the rule that records the answer, so a consumer of the log, such as relayr's follower, tells an `ask_form` answer from an `ask_user` reply or an approval without keeping `run_paused` to join them. It is `null` only on answers recorded before it was. It is a new optional field, so the protocol stays `artifactr.v1`.
- **An answer may be refused by the application.** Core still checks only that the run is paused, the request exists and is unanswered, and its kind matches. The application's check of `answer_deferred` may refuse the answer itself, before it commits ([ADR-0073](0073-checks-that-refuse-a-command-before-it-commits.md)), as `artifactr.ui`'s refuses values that don't fit the form, with a field's error. A refused answer leaves the request open and the run paused, so the person can answer again.
- **A chat message doesn't answer a form.** A message posted while a run is paused answers its questions and declines its approvals, but leaves a form open: only the form's own answer answers it ([ADR-0055](0055-turns-from-the-log.md)'s amendment of the same day).
