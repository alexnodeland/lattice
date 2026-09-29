# ADR-0034: Ports and adapters for integrations

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) connects artifactr to several outside systems: OpenTelemetry's SDK and exporters, Langfuse, LiteLLM, and later evalr. Each is optional, each changes faster than artifactr's rules, and each has alternatives. If the inner layers imported them, every application would carry them, tests would need them, and swapping one would touch the core. reflexr makes the same changes and uses the same vocabulary for them.

## Decision

- **The core stays the hexagon.** `artifactr.core`, `artifactr.telemetry`, `artifactr.workspace` and `artifactr.agent` know nothing of Langfuse, LiteLLM, DSPy or any OpenTelemetry SDK.
- **A port is a small interface owned by the inner layer that needs it:** a `typing.Protocol`, or an existing API that already plays that role (the OpenTelemetry API, pydantic-ai's `Model`).
- **An adapter implements a port in an extra's package**, which depends inward only: its own third-party libraries plus the inner layers. `tests/test_layering.py` enforces it, including that inner layers import only the OpenTelemetry API, never its SDK.
- **Every adapter is tested against a fake** that implements the same port. Where it is cheap, one contract test runs against both.

| Port | Owned by | Adapter | Lives in |
|---|---|---|---|
| The OpenTelemetry API (tracer and meter providers) | `artifactr.telemetry` | The OpenTelemetry SDK, OTLP exporters and instrumentations, set up by `configure_telemetry` | `artifactr.otel` (`[otel]` extra) |
| `Storage` ([ADR-0019](0019-storage-protocol-and-workspace-handles.md)) | `artifactr.workspace` | `SqlStorage` | `artifactr.sql` (`[sql]` extras) |
| A feedback sink, fed by a mirror that follows the log | The inner layers | Langfuse scores | `artifactr.langfuse` (`[langfuse]` extra) |
| A score-config store | The inner layers | Langfuse's score-config API | `artifactr.langfuse` |
| pydantic-ai's `Model` | pydantic-ai | A LiteLLM proxy model, with a capability for per-request metadata | `artifactr.litellm` (`[litellm]` extra) |
| A tenant key resolver and a guardrail policy | `artifactr.litellm` | The application's callbacks | The application |

The surfaces (`artifactr.fastapi`, `artifactr.mcp`) are driving adapters over the same inner layers, as before ([ADR-0022](0022-surfaces-over-one-command-handler.md)).

## Options considered

| Option | Inner layers' dependencies | Swapping a backend |
|---|---|---|
| **Ports in the inner layers, adapters in extras (chosen)** | pydantic, pydantic-ai, the OpenTelemetry API | A new adapter; nothing inside changes |
| Integrations called directly where they are needed | Every backend's client | Edits across layers |
| One plugin registry for every integration | A registry, plus its conventions | Registration, with no typing across it |

## Consequences

- Easier: an application installs only the adapters it uses, and tests run with fakes and no network.
- Easier: each port is small enough to read in one screen, and to implement for another backend.
- Harder: each integration needs a port, an adapter, a fake and, where it matters, a contract test.

## Action items

1. [x] `artifactr.telemetry` over the OpenTelemetry API; layering enforced.
2. [ ] `artifactr.otel`, `artifactr.langfuse` and `artifactr.litellm`, each with its fakes and contract tests (RFC-0002 phases A1, A3 and A7).
