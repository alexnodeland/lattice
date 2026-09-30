# ADR-0038: Feedback as scores, through ports

**Status:** Superseded by [ADR-0049](0049-scores-on-evalr.md)
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

## Amendment (2026-09-29): the mapping and the ports are evalr's

reflexr carried the same mapping and ports, and evalr its own score type, sink and mapping for evaluators' verdicts, so three copies could drift and split one score into two in Langfuse. evalr now owns them (its ADR-0011, from its issue #17), and artifactr keeps only what knows its log.

- **evalr owns the mapping and the ports**, which [ADR-0034](0034-ports-and-adapters-for-integrations.md)'s table gave to the inner layers. `artifactr.scores` calls evalr's `score_configs` and `score_values` with the feedback type's registered name as the `{type}`, and its `ScoreSink` and `ScoreConfigStore` are evalr's. evalr's mapping reproduces this one exactly for every way a feedback type declares a field, and a fixture in evalr pins it, so no score config in Langfuse changes.
- **artifactr keeps the mirror and the adapters.** `FeedbackMirror`, which knows which trace or session each target's feedback belongs on, stays here, with its own score id namespace and ids, so mirroring again replaces the scores already in Langfuse. So do `LangfuseScores` and `LangfuseScoreConfigs`, which now pass evalr's `check_score_sink` and `check_score_config_store`. `sync_score_configs(store, types=None)` keeps its signature and syncs through evalr's.
- **What changed for a score:**
  - A score is evalr's `Score`. Where the feedback came from is its `source`, not its `metadata`; its `metadata` still returns the same keys, and Langfuse receives the same metadata.
  - A sink has one method, `record(scores)`, in place of `send(score)`. The mirror records an envelope's scores at once.
  - A yes or no is a bool, which `LangfuseScores` sends as 1 or 0, as before. A timestamp without a time zone, from an application's clock, is taken to be in UTC.
- **The public names stay, re-exported.** `artifactr.scores` promised `Score`, `ScoreConfig`, `ScoreSink`, `ScoreConfigStore`, `ScoreDataType` and `MAX_TEXT` in its `__all__` and its reference, so it re-exports evalr's (`ScoreDataType` is evalr's `ScoreType`). `score_configs` and `score_values` stay artifactr's own, since they name scores by the registered name. A `ScoreConfig`'s `feedback_type` is now `type_name`.
- **`artifactr.scores` needs evalr.** The `[langfuse]` extra now depends on evalr, as `[evals]` does, pinned by git revision until evalr is published ([ADR-0044](0044-the-evalr-adapter.md)). The inner layers (core, telemetry, workspace, agent) never import evalr; `tests/test_layering.py` lets `artifactr.scores` and `artifactr.langfuse` import `evalr.core`, beside `artifactr.evals`.

reflexr made the same change to `reflexr.scores`, in its ADR-0025.

## Action items

1. [x] `artifactr.scores` and the `Runner`'s `turn_context`.
2. [x] The Langfuse adapter (RFC-0002 phase A3).
3. [x] The mapping and the ports from evalr (2026-09-29 amendment).
