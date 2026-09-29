"""In-memory OpenTelemetry providers, so tests can assert on spans and metrics."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
    NumberDataPoint,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@dataclass
class Recorder:
    """Providers that keep what they record, and helpers to read it back."""

    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    exporter: InMemorySpanExporter
    reader: InMemoryMetricReader

    @property
    def providers(self) -> dict[str, Any]:
        """The providers, as keyword arguments."""
        return {"tracer_provider": self.tracer_provider, "meter_provider": self.meter_provider}

    def spans(self, name: str | None = None) -> list[ReadableSpan]:
        """Finished spans, oldest first, optionally with one name."""
        finished = self.exporter.get_finished_spans()
        return [s for s in finished if name is None or s.name == name]

    def span(self, name: str) -> ReadableSpan:
        """The one finished span with this name."""
        [span] = self.spans(name)
        return span

    def points(self, metric: str) -> list[tuple[dict[str, Any], float]]:
        """A metric's data points: attributes, and the value, sum or count of each."""
        data = self.reader.get_metrics_data()
        found: list[tuple[dict[str, Any], float]] = []
        for resource in data.resource_metrics if data else ():
            for scope in resource.scope_metrics:
                for recorded in scope.metrics:
                    if recorded.name != metric:
                        continue
                    for point in recorded.data.data_points:
                        if isinstance(point, NumberDataPoint):
                            found.append((dict(point.attributes or {}), point.value))
                        elif isinstance(point, HistogramDataPoint):
                            found.append((dict(point.attributes or {}), point.count))
        return found

    def total(self, metric: str, where: dict[str, Any] | None = None) -> float:
        """The sum over a metric's points whose attributes include ``where``."""
        wanted = where or {}
        return sum(
            value
            for recorded, value in self.points(metric)
            if all(recorded.get(key) == value for key, value in wanted.items())
        )


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    yield Recorder(tracer_provider, meter_provider, exporter, reader)
    tracer_provider.shutdown()
    meter_provider.shutdown()


def attributes(span: ReadableSpan) -> dict[str, Any]:
    """A span's attributes as a plain dict."""
    return dict(span.attributes or {})


def trace_id(span: ReadableSpan) -> str:
    """A span's trace id, as 32 hexadecimal digits."""
    assert span.context is not None
    return f"{span.context.trace_id:032x}"
