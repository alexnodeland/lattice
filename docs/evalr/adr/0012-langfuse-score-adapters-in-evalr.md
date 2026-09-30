# ADR-0012: Langfuse score adapters in evalr

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Supersedes the part of [ADR-0011](0011-scores-shared-with-the-libraries.md) that keeps the Langfuse adapters of the score ports in the libraries. The rest of ADR-0011 stands.

## Context

ADR-0011 moved the score mapping and the `ScoreSink` and `ScoreConfigStore` ports into evalr, and kept the feedback mirrors "and their Langfuse adapters" in each library. That left three Langfuse score sinks: evalr's `LangfuseScoreSink`, which records evaluators' scores, and one in each of artifactr's and reflexr's `langfuse/scores.py`, beside a Langfuse `ScoreConfigStore`. The libraries' two files are identical but for a docstring, and evalr's sink already behaves differently from them:

| | evalr's sink | The libraries' sink |
|---|---|---|
| A value not of its data type | Sent with a data type guessed from the value | Refused, and nothing queued |
| The client's calls | In a worker thread, by the rule for synchronous SDKs; `create_score` only enqueues | On the event loop |
| A score with neither a trace nor a session | Refused, and nothing queued | Sent |
| `flush()` | Yes | No |

ADR-0011 kept the adapters beside the mirrors so each library's Langfuse wiring stays in one place. But the adapters know nothing of a library's log; only the mirrors do. It also listed a Langfuse `ScoreConfigStore` in evalr as something to revisit.

## Decision

- **`evalr.langfuse` has the one `ScoreSink` and the one `ScoreConfigStore` over Langfuse**, for evalr's evaluators and the libraries' mirrors alike.
  - `LangfuseScoreSink` is evalr's sink. It calls the client in a worker thread because ADR-0006 runs every synchronous SDK there, not for speed: `create_score` only enqueues. It refuses a batch with a score that has neither a trace nor a session, keeps `flush()`, and records a score's span as Langfuse's observation.
  - `LangfuseScoreConfigStore` is the libraries' store, as it was.
- **`Score` checks its value against its data type**, so no adapter does.
- **The mirrors stay in the libraries**, as ADR-0011 decided, since they read each library's log. The libraries delete their `langfuse/scores.py` and use evalr's adapters.

## Options considered

### Option A: The adapters in evalr (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one sink and one store |
| Coupling | Unchanged: the libraries' `[langfuse]` extras depend on evalr already |
| Drift | None |

**Pros:** one copy, checked by one run of the contract suites; a fix reaches evaluators' and people's scores at once.
**Cons:** a library's Langfuse wiring is split between its mirror and evalr's adapters.

### Option B: An adapter per project (ADR-0011)

| Dimension | Assessment |
|---|---|
| Complexity | Low for each copy, three times over |
| Coupling | None |
| Drift | Already present |

**Pros:** each library's Langfuse wiring in one place.
**Cons:** three sinks that behave differently for the same scores, and two stores, maintained apart.

## Trade-off analysis

The adapters are small and generic: nothing in them is a library's. Keeping copies bought locality at the price of drift, which ADR-0011 set out to end for the mapping, and which had already begun for the sinks. The dependency the move needs exists already.

## Consequences

- Easier: one adapter per port for Langfuse, whose behaviour the contract suites pin for every project.
- Easier: a score whose value is not of its data type fails where it is made, not in a sink.
- Harder: a change to the adapters reaches the libraries only when they move their evalr pin.
- Harder: evalr's online scores attach to the judged span as a Langfuse observation; if the Langfuse exporter filters that span out (v4's default keeps only LLM spans), the score names an observation Langfuse lacks.

## Action items

1. [x] evalr: `LangfuseScoreConfigStore`, one `LangfuseScoreSink`, and the value check in `Score`.
2. [ ] artifactr: delete `langfuse/scores.py`, and use evalr's adapters.
3. [ ] reflexr: the same.
