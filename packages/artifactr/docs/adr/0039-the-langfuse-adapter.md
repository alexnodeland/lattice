# ADR-0039: The Langfuse adapter

**Status:** Accepted; its score adapters superseded by [ADR-0049](0049-scores-on-evalr.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0027](0027-opentelemetry-observability-with-langfuse.md) makes Langfuse the primary observability backend, through a `[langfuse]` extra with a span filter, a context helper, a feedback mirror and score configs. [ADR-0038](0038-feedback-as-scores.md) puts the mirror and score configs behind two ports and gives the `Runner` a `TurnContext` port. [RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) names what each piece does but leaves some details open:

- which scopes the span filter keeps
- how the context helper reaches a turn
- which tags it sets
- how `configure_telemetry(langfuse=True)` wires the client
- what happens when a score config's name is one Langfuse refuses

## Decision

- **`artifactr.langfuse` is an adapter** ([ADR-0034](0034-ports-and-adapters-for-integrations.md)): `LangfuseScores` implements `ScoreSink` with `create_score`, `LangfuseScoreConfigs` implements `ScoreConfigStore` with the score-config API, and `langfuse_turn` implements the `Runner`'s `TurnContext`.
- **The span filter** keeps Langfuse's default (LLM spans, Langfuse's own) and these instrumentation scopes, with their sub-scopes:
  - `artifactr`
  - `pydantic-graph`
  - the MCP SDK's `mcp-python-sdk`, without which an external agent's commits have no root
  - FastAPI and ASGI
  - SQLAlchemy, asyncpg and httpx
- **The turn's attributes are propagated in process, never as baggage**, with `propagate_attributes`:
  - the thread as the session, and the person as the user
  - the trace name `turn`
  - tags `tenant:…`, `workspace:…` and `kind:…` for each kind of artifact the thread follows
  - metadata for the tenant, workspace, thread, run and trigger

  Values are made ASCII and cut to 200 characters. Langfuse's baggage option would put them on outgoing HTTP requests.

- **`configure_telemetry(langfuse=True)` puts Langfuse on the same tracer provider**, as a second span processor with the filter, so the Collector and Langfuse see the same spans, and shuts the client down with the rest. `langfuse_client(...)` does the same for applications that configure the SDK themselves.
- **Score config names Langfuse refuses raise.** Langfuse accepts 35 characters from a small alphabet; a longer `{type}.{field}` raises with the fix (a shorter `name=`), because renaming it silently would break the link between scores and their config.

## Options considered

| Option | Traces whole in Langfuse | Values leave the process |
|---|---|---|
| **Filter plus propagated attributes on the shared provider (chosen)** | Yes | No |
| Langfuse's default filter | No: only model and tool spans | No |
| `propagate_attributes(as_baggage=True)` | Yes | Yes, as HTTP headers on every outgoing request |
| A separate tracer provider for Langfuse | Yes | No, but the Collector and Langfuse see different spans |

## Consequences

- Easier: a turn in Langfuse shows its commits, queries and HTTP calls, filed under its session, user and tenant.
- Harder: Langfuse's filter scopes are a list to keep current as instrumentations are added.

## Action items

1. [x] `artifactr.langfuse`, with contract tests against the port fakes.
