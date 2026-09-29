# ADR-0036: Metric cardinality through SDK views

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) sets a cardinality policy for artifactr's metrics: ids never become attributes, tenant and workspace are attributes by default, and `metrics_detail="workspace" | "tenant" | "none"` limits them for large deployments. It does not say where `metrics_detail` is applied.

artifactr records through the OpenTelemetry API only ([ADR-0034](0034-ports-and-adapters-for-integrations.md)), and `Workspaces`, the `Runner` and the router each record metrics. The SDK has a standard way to limit a metric's attributes before aggregation: a view with `attribute_keys`.

## Decision

- **The library always records the attributes the registry declares**, tenant and workspace included, and nothing else. The registry is the allowlist, so ids cannot reach a metric.
- **`metrics_detail` is applied in the SDK, by views.** `artifactr.telemetry.kept_attributes(metric, detail)` states the policy; `artifactr.otel.metric_views(detail)` turns it into one view per artifactr metric; `configure_telemetry(metrics_detail=...)` installs them. An application that configures the SDK itself passes `metric_views(detail)` to its `MeterProvider`.
- **Duration histograms advise their bucket boundaries** (seconds, from milliseconds to minutes), since the SDK's defaults suit milliseconds.

## Options considered

| Option | Where the level is set | Series before aggregation |
|---|---|---|
| **Views in the SDK (chosen)** | Once, where the SDK is configured | Bounded: views drop attributes before aggregation |
| A `metrics_detail` argument on `Workspaces`, `Runner` and the router | Three times, which can disagree | Bounded |
| Recording without tenancy, adding it at the Collector | The Collector | Tenancy lost for everyone |

## Consequences

- Easier: the library's API has only the providers the RFC names, and the policy lives in one place.
- Easier: views are standard SDK configuration, so other tools read them.
- Harder: an application configuring the SDK by hand must add the views itself to limit detail; without them, it gets the default, tenant and workspace.

## Action items

1. [x] `kept_attributes`, `metric_views` and `configure_telemetry(metrics_detail=...)`.
