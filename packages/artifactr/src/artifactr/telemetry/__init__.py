"""artifactr's tracing and metrics, through the OpenTelemetry API only (ADR-0027).

The API is the port. artifactr records spans and metrics under the ``artifactr`` scope and
never configures the SDK, calls ``Agent.instrument_all()`` or creates a backend client. With
no SDK configured, recording is a no-op. Applications configure the SDK themselves, or with
``artifactr.otel.configure_telemetry`` (the ``[otel]`` extra), which is an adapter.

- :mod:`artifactr.telemetry.attributes` names every attribute artifactr sets.
- :mod:`artifactr.telemetry.metrics` is the metric registry and its cardinality policy.
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
    current_trace_id,
    current_traceparent,
    record_events,
)
from artifactr.telemetry.spans import command_attributes, outcome_attributes

__all__ = [
    "EXTERNAL_METRICS",
    "METRICS",
    "SCOPE",
    "SCOPED",
    "VERSION",
    "Instrument",
    "Metric",
    "MetricsDetail",
    "Telemetry",
    "annotate",
    "attribution",
    "command_attributes",
    "current_trace_id",
    "current_traceparent",
    "kept_attributes",
    "outcome_attributes",
    "record_events",
]
