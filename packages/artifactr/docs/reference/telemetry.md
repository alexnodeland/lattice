# artifactr.telemetry

Tracing and metrics through the OpenTelemetry API. See [Observability](../guides/observability.md).

::: artifactr.telemetry
    options:
      members: false
      show_root_heading: false
      show_root_toc_entry: false

## The metric registry

::: artifactr.telemetry.Metric

::: artifactr.telemetry.METRICS

::: artifactr.telemetry.EXTERNAL_METRICS

::: artifactr.telemetry.MetricsDetail

::: artifactr.telemetry.kept_attributes

::: artifactr.telemetry.SCOPE

::: artifactr.telemetry.SCOPED

## Traces

Which spans are artifactr's, and polling that makes no traces. See [ADR-0046](../adr/0046-telemetry-that-composes-across-libraries.md).

::: artifactr.telemetry.TRACE_SCOPES

::: artifactr.telemetry.is_trace_scope

::: artifactr.telemetry.untraced

## Attributes

::: artifactr.telemetry.attributes
    options:
      show_root_heading: false
      show_root_toc_entry: false

## Recording

These are what artifactr's components record with. Applications rarely need them, except `annotate` and `attribution` to attribute spans of their own.

::: artifactr.telemetry.Telemetry

::: artifactr.telemetry.attribution

::: artifactr.telemetry.annotate

::: artifactr.telemetry.current_trace_id

::: artifactr.telemetry.current_traceparent

::: artifactr.telemetry.record_events

::: artifactr.telemetry.command_attributes

::: artifactr.telemetry.outcome_attributes

::: artifactr.telemetry.VERSION
