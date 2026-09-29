# ADR-0028: Typed feedback as events, mirrored to Langfuse

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

People's reactions (a rating on a turn, a thumbs-down on an artifact version, a note on a thread) are the raw material for evaluation: they show where the agent helps and where it fails, and they seed datasets for training offline evaluators. They need to be as strongly typed as artifacts, scoped to what they are about, and usable both in artifactr's log and in Langfuse next to the traces they judge.

## Decision

- **`Feedback` is a Pydantic base class.** Subclasses register by name and declare the targets they apply to: `artifact` (a version), `thread`, `turn` (a run) and `message`.
- **Feedback is a command and an event.** `give_feedback` goes through the one write path, so it is validated, attributed and replayable, and every surface has it. The fact is recorded as `feedback_given`.
- **Evaluators give feedback too.** An evaluator's verdict is an instance of a feedback type, given by a new actor kind, `EvaluatorActor(name, version)`, so human and evaluator judgements share types and can be compared directly.
- **Langfuse gets scores.** The `[langfuse]` extra mirrors `feedback_given` to Langfuse, one score per field (`{type}.{field}`, typed by the field), with score configs generated from the types. Score ids are derived from the event, so mirroring is idempotent.

## Options considered

| Option | Replayable from the log | In Langfuse beside the traces | Typed |
|---|---|---|---|
| **Typed events, mirrored to Langfuse (chosen)** | Yes | Yes | Yes |
| Langfuse scores only | No | Yes | Partly: score configs |
| The log only | Yes | No | Yes |

## Consequences

- Easier: datasets can be rebuilt from any workspace's log, whatever backend was running.
- Easier: agreement between people and evaluators is a query.
- Harder: every feedback type needs thought about its targets and fields, as artifact types do.

## Action items

1. [ ] Implement RFC-0002 phase A2, and the mirror in phase A3.
