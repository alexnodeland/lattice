# ADR-0044: The evalr adapter

**Status:** Accepted; its amendment superseded by [ADR-0049](0049-scores-on-evalr.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

[ADR-0029](0029-evalr-shared-eval-kit.md) connects artifactr to evalr through an `[evals]` extra that adds datasets from workspace logs, experiment tasks that replay turns, online evaluators run after turns, and the end-to-end measures for chats. [RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) names them, and says `Runner(evaluators=[...])` runs evaluators after turns end, with a sampling rate and a budget, recording their verdicts as feedback from an `EvaluatorActor`. evalr v0.1 supplies the ports: `FeedbackSource`, `Evaluator`, the experiment `Task`, and online evaluation with sampling and budgets (`evalr.online`). Its end-to-end measures read generic inputs (`Session`, `History`, `Transcript`).

Several details were left open:

- how the `Runner` runs evaluators when [ADR-0034](0034-ports-and-adapters-for-integrations.md) forbids the inner layers from importing evalr
- what an example's input is built from, so a judge trained on a dataset sees the same input online
- whose feedback becomes a dataset, now that evaluators write feedback of the same types into the same log
- how a replayed turn starts from the thread as it was
- who wrote an artifact version, for the rewrite rate, when a person accepts an agent's proposal
- how the extra depends on evalr before evalr is published

reflexr's `[evals]` extra made the same kind of choices for workflows; this record follows it where the two libraries overlap.

## Decision

- **`artifactr.evals` is an adapter** ([ADR-0034](0034-ports-and-adapters-for-integrations.md)), and the only package that may import evalr; `tests/test_layering.py` enforces it.
- **The `Runner` gets a port, `TurnEvaluator`**, owned by `artifactr.agent`, as `turn_context` is. `Runner(evaluators=[...])` takes them. As each turn ends, inside its span and after its metrics, the `Runner` hands every evaluator an `EndedTurn` (the session, how the turn ended, and its span's context). `submit` must return at once; a failure it raises is recorded on the turn's span, never raised. The claim on the thread is released as usual, so evaluation never holds up the thread.
- **`OnlineEvaluator` adapts evalr's `OnlineEvaluation` to that port.** It judges completed turns by default, or others by outcome. Sampling (by the run's id, or the thread's when judging threads), the budget and the concurrency limit are evalr's. In the background, it builds the evaluators' input from the turn's context, has evalr judge it, and gives each verdict as feedback with `GiveFeedback`, from `EvaluatorActor(verdict.evaluator, verdict.version)`, through the one write path. Evaluators' verdict types must be feedback types. Score names for evalr's sinks are the registered feedback names. Everything the evaluation does is in the turn's trace. A failure (building the input, an evaluator, a rejected verdict) is recorded on the evaluation's result and logged on `artifactr.evals`, never raised; an evaluator that hands off records nothing.
- **A target's context is read as of the target's end**, not as of the feedback: a turn up to its run's last event, a message up to itself, an artifact version up to the change that made it, a thread up to the feedback. It holds the thread's transcript, the run's events (without the feedback given on it), the artifacts the thread followed then, at their versions then, and for an artifact target the revision and the version as its type. So a dataset built long after a turn gives a judge the input it would have had online, as the turn ended. The trace is the run's latest attempt before that point, or the version's commit ([ADR-0033](0033-trace-links-on-runs-and-revisions.md)).
- **`LogFeedbackSource` builds examples from one feedback type**, with an application builder over a `FeedbackContext`, which is a `TargetContext` with the envelope and the feedback added. So one builder serves datasets and online evaluation. Example ids are the envelopes' ids.
- **Evaluators' feedback is left out of datasets by default** (`include_evaluators=False`), since online evaluators write their verdicts into the same log as the same types, and a judge must not be trained or calibrated on its own verdicts. reflexr's source takes the same option.
- **`replay_task` seeds an isolated in-memory workspace**, per example, from a `Seed` the application builds from it: the artifacts the thread followed (keeping their ids), the thread's mode, then its earlier messages, posted to the log and stored as the agent's model history in one record. The seeding comes before that history, so the agent is not told of it as changes. The prompt is then sent through a `Runner` with the candidate agent, and the output builder gets the turn's run, events, revisions and last message. A failing run fails its item, as evalr's trackers record.
- **A version is written by whoever wrote its content.** An accepted proposal's version is its proposer's; one accepted with the reviewer's own changes counts as two at once, the agent's proposal (rebuilt with `apply_patch` from the version before) and the person's rewrite of it. Archiving changes no text, so it is not a version for the measures. Drop-off reads every envelope of a thread as its activity; people are `user` actors, agents are built-in or external, and the rest (the application, evaluators) are the system.
- **`TaskCompletion` is evalr's `TaskCompletion` as a feedback type**, subclassing both, given on threads, so people and evaluators give the same type and evalr's `completion_rate` reads either. Its docstring stays a judge's instruction. `completion_transcript` builds a judge's input from a context: the first request, the messages, and the followed artifacts as the agent sees them.
- **evalr is pinned by git revision** in `[tool.uv.sources]` while it is unpublished, and the pin is bumped in its own pull requests.

## Options considered

| Option | Inner layers import evalr | Turn slowed or failed by evaluation |
|---|---|---|
| **A `TurnEvaluator` port on the `Runner`, adapted in `artifactr.evals` (chosen)** | No | No |
| `Runner(evaluators=[...])` taking evalr evaluators directly | Yes | No |
| Evaluators as a `TurnContext` | No | Yes: the context is entered inside the turn |
| A log follower that judges `run_ended` events | No | No, but it needs its own task per workspace and cannot record on the turn's span |

| Option for a dataset input | Matches the online input |
|---|---|
| **Read as of the target's end (chosen)** | Yes |
| Read as of the feedback | No: later messages, such as the person's complaint, leak into the input |
| Read as the log is now | No |

## Consequences

- Easier: one input builder trains a judge on people's feedback, measures it, and runs it online, where its verdicts become feedback that the mirror scores like people's.
- Easier: an experiment replays real turns against a new agent without touching production workspaces.
- Harder: a replay starts from the thread's messages, not the original run's tool calls, which a model history rebuilt from text cannot carry.
- Harder: evalr's `drain` returns only evaluations in progress; an application that wants every result reads the task `submit` returns.

## Amendment (2026-09-29): the score mirror uses evalr too

`artifactr.evals` is no longer the only package that imports evalr. The score mapping and ports moved to evalr ([ADR-0038](0038-feedback-as-scores.md), as amended), so `artifactr.scores` and `artifactr.langfuse` import `evalr.core`, and the `[langfuse]` extra depends on evalr. The inner layers still never import it. The git pin in `[tool.uv.sources]` serves both extras and moves in its own pull requests, as before.

## Action items

1. [x] `artifactr.evals`: `LogFeedbackSource` (passing evalr's contract), `replay_task`, `OnlineEvaluator` behind the `Runner`'s `TurnEvaluator`, and the measures (RFC-0002 phase A5).
