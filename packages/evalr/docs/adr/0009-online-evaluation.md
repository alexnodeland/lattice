# ADR-0009: Online evaluation: sampling by key, soft budgets, and events as log records

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 asks for helpers to run evaluators on live traffic "with a sampling rate and a budget", and for an online verdict to be emitted as a `gen_ai.evaluation.result` event "on the span it judged", so evaluation data is not tied to one backend. Three choices were left open:

- **What to sample by.** A random draw per call judges a different share of each run's retries and replays, and cannot be reproduced.
- **How hard a budget is.** A verdict's cost is known only after the evaluation, and evaluations run concurrently.
- **How to emit events.** An OpenTelemetry span event is part of its span and can only be added while the span is open; online evaluation usually runs after the turn or run it judges has ended. The logs API emits events as log records, with any trace and span as their context.

## Decision

- **Sampling is by the input's key** (a turn or run id): an input is judged when `split_bucket(key, salt)` is below the rate, the same hash as dataset splits. The same input is judged in every process, every retry and every replay, or never.
- **Budgets are soft limits per period**, on evaluations, cost, or both: checked before each evaluation and spent after it, so the evaluation that crosses a limit completes. An evaluator that hands off or fails still counts as an evaluation.
- **Evaluations run in the trace of the span they judge**: the span current when `judge` or `submit` is called, or one given, which may already have ended. Their spans nest under it, and their scores record its trace and span.
- **Events are log records.** `OtelEventSink` is a `ScoreSink` that emits one `gen_ai.evaluation.result` event per score through the OpenTelemetry logs API, with the judged trace and span as its context and the GenAI conventions' attributes: the name (`{type}.{field}`), a value or label, and the verdict's text fields as the explanation. It can emit after the span has ended. A score gains an optional `span_id` for it.
- **Online evaluation never breaks the application**: evaluator and sink failures, hand-offs and budget skips are recorded on the result, not raised.

## Options considered

### Sampling

| Option | Reproducible | Same input, same decision |
|---|---|---|
| **By a hash of the key (chosen)** | Yes | Yes |
| A random draw per call | No | No |

### Events

| Option | After the span ends | Needs only the API |
|---|---|---|
| **Log records with the judged span as context (chosen)** | Yes | Yes (`opentelemetry._logs`) |
| Span events on the judged span | No: an ended span takes no events | Yes |
| Spans of their own, linked to the judged span | Yes | Yes, but the conventions define an event |

## Consequences

- Easier: an application samples 10% of turns and knows which, can replay them, and sees every online score both in its backend of choice and as standard OpenTelemetry events.
- Harder: a budget can be overshot by the evaluations in flight when it runs out; for a hard cap, the limit must leave that margin.
- Revisit: the logs API is still underscored (`opentelemetry._logs`) in Python; move with it when it is stabilized.

## Action items

1. [x] Implement `OnlineEvaluation`, `Budget` and `OtelEventSink` (RFC-0001 phase 5).
