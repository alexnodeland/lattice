# ADR-0035: A turn is its own trace

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) traces each turn as an `invoke_workflow turn` span, with the thread as the session, and records each run attempt's trace id. It does not say what a turn's span is a child of.

A turn starts inside something else: the REST request that posted the message, the WebSocket connection it arrived on, the MCP call, or the answer that resumed a paused run. But a run is not bound to what started it ([ADR-0020](0020-running-agents-in-threads.md)): it holds a thread claim, not a socket, so the request returns at once and the run carries on, and a WebSocket connection outlives many turns. As a child of the WebSocket's span, every turn of a long connection would share one trace; as a child of a REST request, the trace's root would end long before its work.

Langfuse models the same thing as one trace per turn, grouped into sessions by `session.id`. Feedback on a turn is attached to that turn's trace ([ADR-0033](0033-trace-links-on-runs-and-revisions.md)).

## Decision

- **Each turn starts a new trace.** The `Runner` starts `invoke_workflow turn` as a root span, with a **span link** to the span that was current when the message or answer arrived, if there was one.
- **The thread is the session** on the turn (`session.id`, `gen_ai.conversation.id`), pydantic-ai's `conversation_id` for the run, and an OpenTelemetry baggage entry (`session.id`) for the turn's duration, so spans from other instrumentation in the turn can carry it.
- **The command that posted the message stays in its request's trace**, and so do all other commands. Only the agent's work moves to the turn's trace.

## Options considered

| Option | One trace per turn | Traces end when their work ends | Request and turn connected |
|---|---|---|---|
| **A root span per turn, linked to its cause (chosen)** | Yes | Yes | Through the link |
| A child of the request or connection | No: a connection's turns share a trace | No | Directly |
| A root span, unlinked | Yes | Yes | Only through the session |

## Consequences

- Easier: a turn is one trace in Tempo and in Langfuse, with its sessions, costs and scores.
- Easier: trace ids per attempt are well defined, so feedback lands on the right trace.
- Harder: following a request to the turn it started means following a link, which Grafana's trace view and Tempo's search both support.
- The baggage entry is copied onto other spans only when the application adds a `BaggageSpanProcessor`, as `configure_telemetry` does. Baggage also travels on outgoing HTTP requests, so it holds the thread id only, never tenant or user ids.

## Action items

1. [x] The `Runner` traces turns, and passes the thread as the conversation id.
