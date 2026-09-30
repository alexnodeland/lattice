"""artifactr's tracing and metrics, through the OpenTelemetry API only (ADR-0027).

The API is the port. artifactr records spans and metrics under the ``artifactr`` scope and
never configures the SDK, calls ``Agent.instrument_all()`` or creates a backend client. With
no SDK configured, recording is a no-op. Applications configure the SDK themselves, or with
``artifactr.otel.configure_telemetry`` (the ``[otel]`` extra), which is an adapter.

- :mod:`artifactr.telemetry.attributes` names every attribute artifactr sets.
- :mod:`artifactr.telemetry.metrics` is the metric registry and its cardinality policy.
- :mod:`artifactr.telemetry.traces` names the spans in artifactr's traces, and runs polling
  untraced.
"""

from artifactr.telemetry.attributes import attribution
from artifactr.telemetry.metrics import (
    EXTERNAL_METRICS,
    METRICS,
    SCOPE,
    SCOPED,
    Instrument,
    Metric,
    MetricsDetail,
    kept_attributes,
)
from artifactr.telemetry.recording import (
    VERSION,
    Telemetry,
    annotate,
    continued,
    current_trace_id,
    current_traceparent,
    record_events,
)
from artifactr.telemetry.spans import command_attributes, outcome_attributes
from artifactr.telemetry.traces import TRACE_SCOPES, is_trace_scope, untraced

__all__ = [
    "EXTERNAL_METRICS",
    "METRICS",
    "SCOPE",
    "SCOPED",
    "TRACE_SCOPES",
    "VERSION",
    "Instrument",
    "Metric",
    "MetricsDetail",
    "Telemetry",
    "annotate",
    "attribution",
    "command_attributes",
    "continued",
    "current_trace_id",
    "current_traceparent",
    "is_trace_scope",
    "kept_attributes",
    "outcome_attributes",
    "record_events",
    "untraced",
]
