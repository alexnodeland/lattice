# ADR-0018: Telemetry through the OpenTelemetry API

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Lattice RFC-0001 asks for spans for checks over a threshold, counters of allowed and refused checks by action, and a copy of each audit event in telemetry. The libraries record through the OpenTelemetry API, the port, and configure no SDK.

## Decision

- **grantr records through the API only,** under the `grantr` scope, and needs no extra; with no SDK configured, recording is a no-op.
- **`grantr.checks` counts checks** by `grantr.action`, `grantr.outcome` and, for a refusal, `grantr.reason` (`unknown_action`, `no_grant` or `store_unreadable`). An action in no catalog is counted as `unknown`, so a caller of `/checks` can't add series by asking about made-up actions. Tenants and subjects are never metric attributes.
- **A check slower than `slow_check` (50 ms by default) is a span,** `grantr.check`, recorded after it ends, from when it started, with its tenant and the action as asked. A fast check leaves no span.
- **Each audit entry is logged** as JSON at the info level on the `grantr.audit` logger, once its change commits, so the stack's logs hold a copy.

## Options considered

| Option | For | Against |
|---|---|---|
| **A span only for a slow check (chosen)** | What the RFC asks; checks stay cheap | A slow check's span starts in the past |
| A span for every check | Every check in traces | A span per command and read on every surface |
| **Audit entries as log records (chosen)** | The stack's logs collect them with no SDK in grantr | Not a trace |

## Consequences

- Easier: a dashboard shows refusals by action and reason without a cardinality surprise.
- Harder: an action from a large custom catalog is still one series per action.
