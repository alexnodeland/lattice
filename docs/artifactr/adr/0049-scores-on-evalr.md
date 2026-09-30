# ADR-0049: Scores on evalr

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

[ADR-0028](0028-typed-feedback-as-events.md) mirrors feedback to evaluation backends as scores, one per field. [ADR-0038](0038-feedback-as-scores.md) decided where the parts live and where a score attaches, and its amendment moved the mapping and the ports to evalr, keeping the mirror, the Langfuse adapters and re-exports of evalr's names in artifactr. Since then evalr has taken the Langfuse adapters too, for its evaluators and the libraries alike, and `Score` checks its own value (evalr's ADR-0012, evalr #34). artifactr's and reflexr's `langfuse/scores.py` were copies of each other, beside a third sink in evalr that behaved differently for the same scores. This record states the decision as it stands, superseding ADR-0038, and the part of [ADR-0039](0039-the-langfuse-adapter.md) that keeps the Langfuse score adapters in `artifactr.langfuse`; the rest of ADR-0039 stands.

## Decision

- **evalr owns scores.** The mapping from a feedback type's fields to `ScoreConfig`s and values, one score per field named `{type}.{field}` and typed by the field; the `Score` and `ScoreConfig` values and `ScoreDataType`; the ports, `ScoreSink` (`record(scores)`) and `ScoreConfigStore` (`names()`, `create(config)`); and their Langfuse adapters, `evalr.langfuse.LangfuseScoreSink` and `LangfuseScoreConfigStore`, which pass evalr's contract suites. A `Score` refuses a value not of its data type, and a span without a trace.
- **artifactr keeps what knows its log.** `artifactr.scores` has `score_configs` and `score_values`, which call evalr's with a feedback type's registered name as the `{type}`; `FeedbackMirror`, which follows a workspace's log; and `sync_score_configs`, which creates the configs a store lacks. It re-exports nothing of evalr's: `Score`, `ScoreConfig`, `ScoreSink`, `ScoreConfigStore`, `ScoreDataType` and `MAX_TEXT` are imported from `evalr.core`.
- **Where a score attaches:**
  - A turn: the trace of the run's latest attempt, the one that ended or paused it.
  - A message: the latest trace of the run that posted it, when the target names the run.
  - An artifact version: the trace it was committed in ([ADR-0033](0033-trace-links-on-runs-and-revisions.md)).
  - A thread, or anything untraced: the session, which is the thread, or the author's thread for an agent's untraced version.
  - A score has a trace or a session, never both, and never a span. Feedback with neither is not scored.
- **Scores are idempotent.** A score's id is a UUIDv5 of the envelope's id and the score's name, in artifactr's namespace, so mirroring the log again replaces the scores already recorded. A mirror keeps a named cursor ([ADR-0046](0046-telemetry-that-composes-across-libraries.md)).
- **Where the feedback came from is the score's `source`:** the tenant, workspace, feedback type, target, actor and `seq`. A score has no evaluator, even for an evaluator's verdict, whose actor is in its source.
- **evalr is needed for scores.** The `[langfuse]` extra depends on `evalr[langfuse]` and `[evals]` on evalr, pinned by git revision until evalr is published ([ADR-0044](0044-the-evalr-adapter.md)). The inner layers never import evalr; `tests/test_layering.py` lets only `artifactr.scores` and `artifactr.evals` import it.
- **A `TurnContext` port on the `Runner`,** entered around each turn, lets `artifactr.langfuse` attribute turns without the `Runner` knowing Langfuse. It stays artifactr's.

## Options considered

| Option | Assessment |
|---|---|
| **evalr's adapters, used from evalr (chosen)** | One sink and one store for every project, checked by one run of the contract suites |
| An adapter per project (ADR-0038's amendment) | Three sinks that behave differently for the same scores, maintained apart |
| evalr's adapters, re-exported by artifactr | One implementation, but two names for it, and a list to keep in step with evalr's |
| The mirror in evalr too | One mirror, but evalr would read each library's log |

The mirror stays here because only artifactr knows which trace or session a piece of feedback belongs on.

## Consequences

- Easier: one Langfuse sink and store for evaluators' scores and people's, pinned by one run of evalr's contract suites; a person's `helpfulness.rating` and an evaluator's are the same score.
- Easier: a score whose value is not of its type fails where it is made, not in a sink.
- Harder: a change to the adapters reaches artifactr only when it moves its evalr pin.
- Harder: an application's Langfuse wiring imports from `artifactr.langfuse` (traces and turns) and `evalr.langfuse` (scores).
- Harder: each workspace to mirror needs a mirror task.

## Action items

1. [x] Use evalr's Langfuse adapters, delete `artifactr.langfuse`'s, and pin evalr at `7a290123`.
2. [x] Drop `artifactr.scores`' re-exports of evalr's names.
