# ADR-0046: Telemetry that composes across libraries, untraced polling and mirror cursors

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

## Context

stackr's template runs artifactr and reflexr in one application, and each library's `[otel]` helper assumed it was alone ([#50](https://github.com/alexnodeland/artifactr/issues/50)):

- An application could call only one `configure_telemetry`, so the other library's metric views and span filter were lost.
- `langfuse=True` exported spans straight to Langfuse, which stackr's Collector already sends it.
- Subscriptions and feedback mirrors poll storage, and each poll's queries were a trace of their own.
- A `FeedbackMirror` kept no cursor, so every restart mirrored the whole log again.

reflexr makes the same decision, with the same API, in [reflexr ADR-0040](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0040-telemetry-that-composes-across-libraries.md).

## Decision

- **Each library contributes to one telemetry setup.** `artifactr.otel.telemetry()` returns a `Contribution`: its `name`, `metric_views(detail)`, `should_export_span(span)`, and the instrumentations it advises, `instrument`. Either library's `configure_telemetry(*contributions, ...)` takes the others' contributions and adds its own, keeping one per name. Views are concatenated, and Langfuse keeps a span if any contribution keeps it. Neither library imports the other ([ADR-0034](0034-ports-and-adapters-for-integrations.md)): `configure_telemetry` reads contributions through the `TelemetryContribution` protocol, whose four fields both libraries share. `MetricsDetail` (`"workspace"`, `"tenant"` or `"none"`) is part of that contract, and `instrument` is typed as names, so neither library's types depend on the other's.
- **artifactr advises the FastAPI, SQLAlchemy and httpx instrumentations,** and `configure_telemetry` instruments those advised, unless told which. asyncpg is left out: under SQLAlchemy it recorded every query twice.
- **`langfuse="traces"` or `"scores"`.** `"scores"` exports no spans to Langfuse, for a Collector that already sends it every trace; the client still sets each turn's session, user and tags, and sends scores.
- **Polling is untraced.** `artifactr.telemetry.untraced()` starts every span in its block as a child of a span that is never sampled. Subscriptions read the log in it, and the feedback mirror runs in it, so an idle application exports no spans. What a poll finds, such as a commit, is traced where it happens, never inside `untraced()`, whose trace ids belong to the unsampled parent.
- **Consumers of the log keep cursors.** `Storage` gains `cursor(scope, name)` and `save_cursor(scope, name, seq)`, and a cursor only moves forward. A `FeedbackMirror` starts after its cursor, whose name it is always given: two mirrors sharing a name would skip feedback after a restart. It saves the cursor after it records a piece of feedback's scores, and after every 500 other envelopes. Mirroring stays at least once: scores are keyed, so a repeat replaces them.

## Options considered

For polling:

| Option | An idle application exports | Metrics recorded in a poll |
|---|---|---|
| **A parent that is never sampled (chosen)** | Nothing, under a parent-based sampler, the SDK's default | Kept |
| OpenTelemetry's `suppress_instrumentation` | Nothing | Dropped: SQLAlchemy's pool metric misses the connections polls open |
| Polls as children of a recorded long-lived span | Every poll's spans, in a trace that ends at shutdown | Kept |

`suppress_instrumentation` also lives in `opentelemetry-instrumentation`, which the inner layers don't depend on.

For composing, the alternative was to keep single-library helpers and have each application compose the views and span filters itself. Every application that uses both libraries would then repeat that work.

## Consequences

- Easier: an application configures telemetry once for both libraries, can trace its database again, and sends Langfuse no span twice.
- Harder: the contribution's fields and the cursor's meaning are kept identical in both libraries by review.
- Harder: a sampler that ignores the parent, such as `always_on` or `traceidratio`, traces each poll again.

## Action items

1. [x] `telemetry()`, `configure_telemetry(*contributions)`, `langfuse="traces" | "scores"`, `untraced()`, and storage cursors.
2. [ ] stackr's template: configure telemetry with both contributions and `langfuse="scores"`, and drop its own span filter.
