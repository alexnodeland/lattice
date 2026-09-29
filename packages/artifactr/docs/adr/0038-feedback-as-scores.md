# ADR-0038: Feedback as scores, through ports

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0028](0028-typed-feedback-as-events.md) mirrors feedback to Langfuse as scores, one per field (`{type}.{field}`, typed by the field), with score configs generated from the types and score ids derived from the event. [ADR-0034](0034-ports-and-adapters-for-integrations.md) puts backends behind ports. [RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) says turn and message feedback goes to the turn's trace, thread feedback to the session, and artifact feedback to the trace of the run that wrote that version and to the session. It also asks for a per-turn context helper for Langfuse. Several details were left open:

- where the backend-neutral parts live
- which trace a turn's feedback belongs to, when the run paused and resumed
- how a score targets "a trace and a session"
- how a backend attributes a turn without the `Runner` depending on it

## Decision

- **`artifactr.scores` is an inner package** with no backend in it:
  - The pure mapping from feedback types to `ScoreConfig`s and from feedback values to scores.
  - Two ports: `ScoreSink` (`send(score)`, idempotent by the score's id) and `ScoreConfigStore` (`names()`, `create(config)`).
  - `FeedbackMirror`, a subscriber on one workspace's log that sends each `feedback_given`'s scores to a sink.
  - `sync_score_configs`, which creates missing configs in a store.
- **Where a score attaches:**
  - A turn: the trace of the run's latest attempt, the one that ended or paused it.
  - A message: the latest trace of the run that posted it, when the target names the run.
  - An artifact version: the trace it was committed in ([ADR-0033](0033-trace-links-on-runs-and-revisions.md)).
  - A thread, or anything untraced: the session, which is the thread, or the author's thread for an agent's untraced version.
  - A score has a trace or a session, never both: a trace already belongs to its session. Feedback with neither is not scored.
- **Scores are idempotent.** A score's id is a UUIDv5 of the envelope's id and the score's name, so a mirror can always start over from the beginning of the log.
- **Values:** booleans are 1 or 0, numbers are floats, categories and text are strings (text cut at 500 characters), and fields without a value are skipped. A feedback type the mirroring process does not register is skipped.
- **A `TurnContext` port on the `Runner`:** an async context the `Runner` enters around each turn, inside its span, given the run's session. The Langfuse adapter uses it to propagate trace attributes; the `Runner` knows nothing of Langfuse.

## Options considered

| Option | Backend in the inner layers | Precise for resumed runs |
|---|---|---|
| **Inner mapping and mirror, backend adapters behind two ports (chosen)** | None | Yes |
| All of it in `artifactr.langfuse` | None, but other backends rebuild the mirror | Yes |
| Scores built by core as part of `give_feedback` | None, but core grows a backend concept | Yes |

## Consequences

- Easier: a new evaluation backend needs a `ScoreSink` of a few lines; the mapping, targeting and idempotency come with the mirror.
- Easier: the fakes in the tests are the reference implementations of the ports.
- Harder: each workspace to mirror needs a mirror task. Applications with many workspaces start them as workspaces become active.

## Action items

1. [x] `artifactr.scores` and the `Runner`'s `turn_context`.
2. [ ] The Langfuse adapter (RFC-0002 phase A3).
