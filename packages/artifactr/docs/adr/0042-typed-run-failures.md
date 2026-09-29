# ADR-0042: Typed run failures

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) wants a request blocked by an LLM gateway's guardrail to be a typed, recorded outcome: the run fails with a `guardrail_blocked` reason, rather than with an opaque HTTP error. Until now a run that raised was recorded as `run_ended` with status `failed` and the exception's text, and nothing a client or a dashboard could count on. Guardrails are one case; a tool that refuses on policy grounds is another.

The agent layer must not know about LiteLLM ([ADR-0034](0034-ports-and-adapters-for-integrations.md)).

## Decision

- **`run_ended` has an optional `reason`**: a short, stable code for why a failed run failed (an additive change to protocol v1).
- **`artifactr.agent.RunFailure(message, reason=...)`** is an exception for tools and capabilities to raise. `ArtifactWorkspace` records a run that raised one as `failed` with its `reason` and message; any other exception is recorded as before, without a reason.
- **`artifactr.runs` carries the reason** (`artifactr.run.reason`), a bounded attribute because reasons are codes, and the Agent and LLM dashboard shows failed runs by reason.

## Options considered

| Option | Typed on the wire | Agent layer knows the gateway |
|---|---|---|
| **A `reason` on `run_ended`, from a `RunFailure` exception (chosen)** | Yes | No |
| A new `run_blocked` event | Yes, but one event per kind of failure | No |
| Parsing the error text in clients | No | No |

## Consequences

- Easier: clients and dashboards tell a guardrail block from a crash, and any capability can add its own reasons.
- Harder: reasons are codes shared by convention; each adapter documents the ones it uses.

## Action items

1. [x] `RunEnded.reason`, `RunFailure`, the metric attribute and the dashboard panel.
2. [x] `guardrail_blocked`, from the `[litellm]` extra (RFC-0002 phase A7).
