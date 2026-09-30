# ADR-0027: OpenTelemetry-native observability, with Langfuse primary

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr's agents need to be observable end to end: the chat turn, the agent run, model calls and tool calls, and also the database and HTTP work around them, so a slow or failing turn can be explained. The tooling should be open. Pydantic's Logfire traces all of this in one place, and is the model to borrow from, but it is a paid platform. Langfuse is open source and self-hostable, is built on OpenTelemetry, and understands sessions, scores, datasets and experiments.

A research spike (2026-09-28) against the installed packages found:

- Langfuse 4.15 exports only LLM spans unless given `should_export_span`.
- pydantic-ai 2.51's instrumentation is a capability, and emits `gen_ai.conversation.id`, which Langfuse reads as the session.
- Libraries should depend on the OpenTelemetry API only.

## Decision

- **OpenTelemetry is the substrate.** artifactr depends on `opentelemetry-api` and emits spans and metrics under its own scope, with optional tracer and meter providers. It never configures the SDK.
- **GenAI conventions and attribution.** Spans follow the GenAI conventions (`invoke_workflow turn`, pydantic-ai's `invoke_agent` and `execute_tool`). artifactr adds tenant, workspace, thread, run and actor attributes, with the thread as the session (`session.id` and `gen_ai.conversation.id`). Runs persist the trace ids of their attempts.
- **Metrics come from a registry**, with a cardinality policy: ids never become metric attributes; tenant and workspace are configurable. Grafana dashboards ship in the repository, tested against the registry.
- **Langfuse is the primary backend**, through a `[langfuse]` extra: a span filter that keeps whole traces, a context helper, a feedback mirror and score configs.
- **Grafana's LGTM stack plus Pyroscope** is the full-application view, fed by an OpenTelemetry Collector that also exports to Langfuse.
- **Logfire is supported, not primary:** a documented recipe, never a dependency.
- An **`[otel]` extra** provides `configure_telemetry(...)` so applications set up the SDK, exporters and instrumentations in one call.

## Options considered

| Option | Open | Full-application traces | LLM features (sessions, scores, experiments) |
|---|---|---|---|
| **OTel API, Langfuse primary, LGTM and Pyroscope (chosen)** | Yes | Yes, in Tempo and Langfuse | Yes, in Langfuse |
| Logfire primary | No: a paid platform | Yes | Partial |
| The Langfuse SDK in core | Yes | Partial: its default filter drops non-LLM spans | Yes, but it forces the OTel SDK and a global provider |
| SigNoz instead of LGTM | Yes | Yes | No: needs Langfuse beside it anyway |

## Consequences

- Easier: one trace connects a person's message to every model, tool, database and HTTP call it caused, in both Grafana and Langfuse.
- Easier: any OTLP backend works; Langfuse and Grafana are defaults, not requirements.
- Harder: the GenAI conventions are still in development, so their attribute names live in one constants module.

## Action items

1. [x] Implement RFC-0002 phases A1, A3 and A4.
