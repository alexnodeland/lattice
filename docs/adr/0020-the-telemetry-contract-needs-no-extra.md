# ADR-0020: The telemetry contract needs no extra

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland
**Amends:** [ADR-0018](0018-lattice-core-what-the-libraries-share.md): where the OpenTelemetry contract lives in lattice-core, and the Langfuse client, which stays in each library

## Context

ADR-0018's third step moved artifactr's and reflexr's OpenTelemetry setup into `lattice_core.otel`, behind the `otel` extra. With it went the contract between a library and `configure_telemetry`: `Contribution`, the `TelemetryContribution` port, `MetricsDetail` and `Instrumented` ([artifactr ADR-0046](../artifactr/adr/0046-telemetry-that-composes-across-libraries.md)). Behind the extra, the contract could not reach the code that needs it most:

- each library's `telemetry` layer records through OpenTelemetry's API alone, never the SDK, and defined its own `MetricsDetail`;
- relayr's contribution copied `Contribution` and `MetricsDetail`, "as the libraries' `MetricsDetail` says".

Nothing of lattice-core is published yet, so where the contract lives can still change without a deprecation.

ADR-0018 also listed the Langfuse client among the code copied word for word. It only looks alike: each library's `langfuse_client` defaults its span filter to that library's own `should_export_span`.

## Decision

- **The contract is `lattice_core.otel.contribution`, which needs no extra.** It names the SDK's `View` and `ReadableSpan` only in its annotations, under `TYPE_CHECKING`, so it imports with nothing but lattice-core's base installed. `lattice_core.otel.configure`, the `otel` extra, imports the contract from it, and nothing else defines its names.
- **Its users take it from there.** artifactr's and reflexr's `telemetry` layers take `MetricsDetail` from it; their `otel` modules re-export `Contribution`, `TelemetryContribution` and `Instrumented`. relayr's contribution is a lattice-core `Contribution`, and `relayr.otel` re-exports it with `MetricsDetail`; relayr's `otel` extra requires lattice-core.
- **The `otel/` subpackage holds both modules,** the contract and the setup, so every OpenTelemetry name in lattice-core is under one path. The layering test lists the modules inside an extra's subpackage that need no extra, and finds every other such module itself.
- **The setup's optional imports stay lazy.** `lattice_core.otel.configure` imports FastAPI, SQLAlchemy, Langfuse and `lattice_core.langfuse` only inside a function or under `TYPE_CHECKING`, and the layering test checks it. Each extra's modules import in a fresh interpreter with the other extras' packages missing.
- **`langfuse_client` stays in each library,** since its default filter is that library's. lattice-core holds the filters it composes, `span_filter` and `no_spans`, and `configure_telemetry(langfuse=...)` builds its own client from them.

## Options considered

| Option | For | Against |
|---|---|---|
| **A module of its own, needing no extra (chosen)** | The telemetry layers and relayr name the contract without the SDK; one definition | One more module |
| Keep it in `lattice_core.otel.configure` | No change | The telemetry layers can't import it, so `MetricsDetail` stays defined three times, and relayr's `Contribution` twice |
| A top-level `lattice_core.telemetry` | A shorter path | lattice-core's OpenTelemetry names in two places |
| The contract importing the SDK at run time | No `TYPE_CHECKING` | The libraries' base installs would need the SDK, which their ports keep out ([artifactr ADR-0034](../artifactr/adr/0034-ports-and-adapters-for-integrations.md)) |

## Consequences

- Easier: a contribution's shape is defined once, and a library's telemetry layer, relayr and an application all build on it.
- Easier: the layering test holds `configure`'s optional imports lazy, so an application without FastAPI or SQLAlchemy can still configure telemetry.
- Harder: `MetricsDetail` in artifactr and reflexr is now lattice-core's, re-exported; reflexr's was a `type` statement, and is now a plain alias of the same three values.
