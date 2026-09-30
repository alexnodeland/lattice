# ADR-0037: Feedback targets and evaluators

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0028](0028-typed-feedback-as-events.md) makes feedback a typed command and event, with four targets (an artifact version, a thread, a turn, a message) and an evaluator actor. [RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) names the targets `ArtifactTarget(artifact_id, version)`, `ThreadTarget(thread_id)`, `TurnTarget(run_id)` and `MessageTarget(message_id)`, and says core validates the type and the target. Some details were left open:

- **Messages are not entities.** They exist only as `message_posted` events, so core cannot check that a message exists, and nothing links a message to the run and trace that produced it without scanning the log.
- **What an evaluator may do** beyond giving feedback.
- **The event's shape**, which reflexr's `feedback_given` must match (RFC-0002's shared conventions).

## Decision

- **A message target names its thread, and optionally its run:** `MessageTarget(message_id, thread_id, run_id=None)`. A client has both from the message's `message_posted`. Core checks the thread exists, and that the run, when given, exists in that thread. The message id itself is recorded, not checked.
- **An artifact target must name a version that exists:** from 1 to the artifact's current version, archived or not.
- **A turn target is a run**, which may span pauses; its feedback belongs to the run's thread.
- **The event carries its scope.** `feedback_given` has the thread and run its target belongs to, so it reaches the thread's subscribers; feedback on an artifact version is workspace-scoped, like artifact events.
- **An evaluator only gives feedback.** Every other command from an `EvaluatorActor` is forbidden. Each version of an evaluator is its own participant (`evaluator:{name}@{version}`), so verdicts from different versions never mix.
- **Shared with reflexr:** the event's fields are `feedback_type`, `target` (discriminated by `kind`) and `value`, and feedback types register with `name=` and `targets=` as reflexr's do. There is no feedback id: the envelope's id identifies the feedback, and Langfuse score ids are derived from it.

## Options considered

| Option | Checks the target | Finds the message's trace |
|---|---|---|
| **Thread and optional run on the message target (chosen)** | Thread and run | From the run's traces |
| `MessageTarget(message_id)` only | Nothing | Only by scanning the log |
| Messages as stored entities | The message | Directly, at the cost of a new entity and migration |

## Consequences

- Easier: every target is checked against entities core already loads, with no log scans.
- Easier: feedback on the agent's message reaches the trace of the run that posted it.
- Harder: a client must send the message's thread, and its run for the agent's messages.
- A feedback event for a message that never existed, in a real thread, is not caught.

## Action items

1. [x] Feedback types, targets, `give_feedback`, `feedback_given` and `EvaluatorActor`, with conformance cases.
