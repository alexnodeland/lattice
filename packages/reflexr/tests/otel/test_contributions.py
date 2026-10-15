"""Libraries' contributions compose: one telemetry setup for reflexr and a sibling library.

artifactr is not installed here (ADR-0003: neither library depends on the other). A stand-in
with the same four fields, a class of its own and not reflexr's ``Contribution``, shows that
``configure_telemetry`` reads a contribution structurally, as it reads artifactr's.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import pytest
from langfuse import propagate_attributes
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from reflexr.otel import Contribution, TelemetryHandle, configure_telemetry
from reflexr.telemetry import SCOPE, Telemetry
from reflexr.telemetry.attributes import EVENT_TYPE, TENANT_ID
from reflexr.telemetry.metrics import EVENTS_PUBLISHED
from tests.langfuse.conftest import FakeLangfuseApi

type Detail = Literal["workspace", "tenant", "none"]

SIBLING_TENANT, SIBLING_WORKSPACE = "artifactr.tenant.id", "artifactr.workspace.id"


@dataclass(frozen=True)
class SiblingTelemetry:
    """A stand-in for ``artifactr.otel.telemetry()``: the same fields, in a class of its own."""

    name: str
    metric_views: Callable[[Detail], Sequence[View]]
    should_export_span: Callable[[ReadableSpan], bool]
    instrument: frozenset[Literal["fastapi", "sqlalchemy", "asyncpg", "httpx"]]


def sibling_views(detail: Detail) -> list[View]:
    tenancy = {"workspace": {SIBLING_TENANT, SIBLING_WORKSPACE}, "tenant": {SIBLING_TENANT}}
    keys = {"artifactr.command.type", *tenancy.get(detail, set[str]())}
    return [View(instrument_name="artifactr.commands", meter_name="artifactr", attribute_keys=keys)]


def in_siblings_traces(span: ReadableSpan) -> bool:
    scope = span.instrumentation_scope
    return scope is not None and scope.name == "artifactr"


SIBLING = SiblingTelemetry(
    name="artifactr",
    metric_views=sibling_views,
    should_export_span=in_siblings_traces,
    instrument=frozenset({"fastapi", "sqlalchemy", "httpx"}),
)

QUIET: dict[str, Any] = {"instrument": (), "logs": False, "set_global": False}


def points(reader: InMemoryMetricReader, name: str) -> list[dict[str, Any]]:
    data = reader.get_metrics_data()
    return [
        dict(point.attributes or {})
        for resource in (data.resource_metrics if data else ())
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


def publish(handle: TelemetryHandle) -> None:
    """Record one of reflexr's metrics, as a workspace does when an event is published."""
    Telemetry(meter_provider=handle.meter_provider).record(
        EVENTS_PUBLISHED,
        1,
        tenant_id="t1",
        workspace_id="w1",
        attributes={EVENT_TYPE: "app:deploy.finished"},
    )


def test_every_librarys_views_apply_the_level_of_detail() -> None:
    reader = InMemoryMetricReader()
    with configure_telemetry(
        SIBLING,
        service_name="app",
        metrics_detail="tenant",
        span_exporter=InMemorySpanExporter(),
        metric_reader=reader,
        **QUIET,
    ) as handle:
        publish(handle)
        commands = handle.meter_provider.get_meter("artifactr").create_counter("artifactr.commands")
        commands.add(
            1,
            {SIBLING_TENANT: "t1", SIBLING_WORKSPACE: "w1", "artifactr.command.type": "create"},
        )
        [reflexrs] = points(reader, "reflexr.events.published")
        [siblings] = points(reader, "artifactr.commands")
    assert set(reflexrs) == {TENANT_ID, EVENT_TYPE}, "reflexr's own views are kept"
    assert set(siblings) == {SIBLING_TENANT, "artifactr.command.type"}, "the sibling's apply too"


def test_an_applications_contribution_named_reflexr_replaces_its_own() -> None:
    mine = Contribution(
        name=SCOPE,
        metric_views=lambda detail: [],
        should_export_span=lambda span: False,
        instrument=frozenset(),
    )
    reader = InMemoryMetricReader()
    with configure_telemetry(
        mine,
        service_name="app",
        metrics_detail="none",
        span_exporter=InMemorySpanExporter(),
        metric_reader=reader,
        logs=False,
        set_global=False,
    ) as handle:
        publish(handle)
        [point] = points(reader, "reflexr.events.published")
    assert TENANT_ID in point, "reflexr's views were replaced by the application's own, none"


def telemetry_with(*contributions: Any, **options: Any) -> TelemetryHandle:
    return configure_telemetry(
        *contributions,
        service_name="app",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
        logs=False,
        set_global=False,
        **options,
    )


def test_reflexr_advises_sqlalchemy_not_asyncpg() -> None:
    with telemetry_with():
        assert SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry
        assert not AsyncPGInstrumentor().is_instrumented_by_opentelemetry, (
            "SQLAlchemy's spans already cover the queries asyncpg runs"
        )


class Langfuse:
    """configure_telemetry's options for a Langfuse client on an in-process Langfuse API."""

    def __init__(self) -> None:
        self.api = FakeLangfuseApi()
        self.spans = InMemorySpanExporter()

    def options(self) -> dict[str, Any]:
        return {
            "public_key": f"pk-lf-{uuid.uuid4()}",
            "secret_key": "sk-lf-test",
            "base_url": "http://langfuse.test",
            "httpx_client": httpx.Client(transport=httpx.MockTransport(self.api.handle)),
            "span_exporter": self.spans,
        }


@pytest.fixture
def langfuse() -> Langfuse:
    return Langfuse()


def spans_from(handle: TelemetryHandle, *scopes: str) -> None:
    for scope in scopes:
        tracer = handle.tracer_provider.get_tracer(scope)
        with propagate_attributes(session_id="evt_1"), tracer.start_as_current_span(scope):
            pass
    with handle.tracer_provider.get_tracer("other.llm").start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
    handle.tracer_provider.force_flush()
    assert handle.langfuse is not None
    handle.langfuse.flush()


def test_langfuse_keeps_a_span_any_library_keeps(langfuse: Langfuse) -> None:
    collector = InMemorySpanExporter()
    with configure_telemetry(
        SIBLING,
        service_name="app",
        span_exporter=collector,
        metric_reader=InMemoryMetricReader(),
        langfuse="traces",
        langfuse_options=langfuse.options(),
        **QUIET,
    ) as handle:
        spans_from(handle, "reflexr", "artifactr", "opentelemetry.instrumentation.fastapi", "noise")
    kept = [span.name for span in langfuse.spans.get_finished_spans()]
    assert kept == ["reflexr", "artifactr", "opentelemetry.instrumentation.fastapi", "chat"]
    assert len(collector.get_finished_spans()) == 5, "the Collector gets every span"
