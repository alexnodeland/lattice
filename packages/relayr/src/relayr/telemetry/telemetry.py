"""The tracer and counters relayr records with, through the OpenTelemetry API only.

Without an SDK configured every span and measurement is a no-op, as in the libraries; an
application configures the SDK, with `relayr.otel.telemetry()` among its contributions.
"""

from collections.abc import Mapping
from importlib.metadata import version

from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, MeterProvider
from opentelemetry.trace import Link, Tracer, TracerProvider, get_current_span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util.types import AttributeValue

from relayr.telemetry.attributes import TENANT_ID, WORKSPACE_ID
from relayr.telemetry.metrics import METRICS, SCOPE, Metric

_W3C = TraceContextTextMapPropagator()


class Telemetry:
    """relayr's tracer, and a counter for every metric in the registry.

    Args:
        tracer_provider: Where spans go. Defaults to the global provider.
        meter_provider: Where metrics go. Defaults to the global provider.
    """

    def __init__(
        self,
        *,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        release = version("relayr-ai")
        self.tracer: Tracer = trace.get_tracer(SCOPE, release, tracer_provider)
        meter = metrics.get_meter(SCOPE, release, meter_provider)
        self._counters: dict[str, Counter] = {
            name: meter.create_counter(name, unit=metric.unit, description=metric.description)
            for name, metric in METRICS.items()
        }

    def count(self, metric: Metric, attributes: Mapping[str, AttributeValue]) -> None:
        """Add one to a counter, with only the attributes it may carry."""
        kept = {key: value for key, value in attributes.items() if key in metric.attributes}
        self._counters[metric.name].add(1, kept)


def workspace_attributes(tenant_id: str, workspace_id: str) -> dict[str, AttributeValue]:
    """The attributes that attribute work to a workspace."""
    return {TENANT_ID: tenant_id, WORKSPACE_ID: workspace_id}


def linked(traceparent: str | None) -> list[Link]:
    """A link to the span a W3C `traceparent` names, if it names a valid one."""
    if traceparent is None:
        return []
    span = get_current_span(_W3C.extract({"traceparent": traceparent})).get_span_context()
    return [Link(span)] if span.is_valid else []
