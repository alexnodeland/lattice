"""A library's contribution, a sibling's, and in-memory exporters, for configure_telemetry."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lattice_core.otel.configure import (
    Contribution,
    MetricsDetail,
    TelemetryHandle,
    configure_telemetry,
)

TENANT = "demo.tenant.id"
WORKSPACE = "demo.workspace.id"
KIND = "demo.kind"
REQUESTS = "demo.requests"


def demo_views(detail: MetricsDetail) -> list[View]:
    kept = {"workspace": {TENANT, WORKSPACE}, "tenant": {TENANT}}.get(detail, set[str]())
    return [View(instrument_name=REQUESTS, meter_name="demo", attribute_keys={KIND, *kept})]


def in_demos_traces(span: ReadableSpan) -> bool:
    return span.instrumentation_scope is not None and span.instrumentation_scope.name == "demo"


DEMO = Contribution(
    name="demo",
    metric_views=demo_views,
    should_export_span=in_demos_traces,
    instrument=frozenset({"fastapi", "sqlalchemy", "httpx"}),
)
"""A library's own contribution, as its configure_telemetry passes it."""

type Detail = Literal["workspace", "tenant", "none"]


@dataclass(frozen=True)
class SiblingTelemetry:
    """Another library's contribution: the same fields, in a class of its own."""

    name: str
    metric_views: Callable[[Detail], Sequence[View]]
    should_export_span: Callable[[ReadableSpan], bool]
    instrument: frozenset[Literal["fastapi", "sqlalchemy", "asyncpg", "httpx"]]


def sibling_views(detail: Detail) -> list[View]:
    kept = {"workspace": {"rule", TENANT, WORKSPACE}, "tenant": {"rule", TENANT}}
    keys = kept.get(detail, {"rule"})
    return [View(instrument_name="sibling.firings", meter_name="sibling", attribute_keys=keys)]


def in_siblings_traces(span: ReadableSpan) -> bool:
    return span.instrumentation_scope is not None and span.instrumentation_scope.name == "sibling"


SIBLING = SiblingTelemetry(
    name="sibling",
    metric_views=sibling_views,
    should_export_span=in_siblings_traces,
    instrument=frozenset({"fastapi", "sqlalchemy", "httpx"}),
)


class Captured:
    """In-memory exporters and a reader, to pass to configure_telemetry."""

    def __init__(self) -> None:
        self.spans = InMemorySpanExporter()
        self.reader = InMemoryMetricReader()
        self.logs = InMemoryLogRecordExporter()

    def options(self) -> dict[str, Any]:
        return {
            "span_exporter": self.spans,
            "metric_reader": self.reader,
            "log_exporter": self.logs,
            "set_global": False,
        }

    def points(self, name: str) -> list[dict[str, Any]]:
        data = self.reader.get_metrics_data()
        return [
            dict(point.attributes or {})
            for resource in (data.resource_metrics if data else ())
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == name
            for point in metric.data.data_points
        ]


@pytest.fixture
def captured() -> Captured:
    return Captured()


@pytest.fixture
def handle(captured: Captured) -> Iterator[TelemetryHandle]:
    with configure_telemetry(
        DEMO,
        service_name="docplan",
        service_version="1.2.3",
        environment="test",
        **captured.options(),
    ) as handle:
        yield handle
