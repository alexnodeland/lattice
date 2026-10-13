"""reflexr's configure_telemetry: its own contribution, on the setup lattice-core tests."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from opentelemetry import baggage
from opentelemetry import context as otel_context
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text

from reflexr.otel import (
    URL_ATTRIBUTES,
    TelemetryHandle,
    configure_telemetry,
    metric_views,
)
from reflexr.sql import create_sqlite_engine
from reflexr.telemetry import SCOPE, Telemetry
from reflexr.telemetry.attributes import EVENT_TYPE, SESSION_ID, TENANT_ID, WORKSPACE_ID
from reflexr.telemetry.metrics import EVENTS_PUBLISHED


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
        service_name="oncall", service_version="1.2.3", environment="test", **captured.options()
    ) as handle:
        yield handle


def test_spans_carry_the_service_and_the_runs_session(
    handle: TelemetryHandle, captured: Captured
) -> None:
    tracer = handle.tracer_provider.get_tracer("test")
    token = otel_context.attach(
        baggage.set_baggage("user.id", "alice", baggage.set_baggage(SESSION_ID, "evt_1"))
    )
    try:
        with tracer.start_as_current_span("query"):
            pass
    finally:
        otel_context.detach(token)
    handle.tracer_provider.force_flush()
    [span] = captured.spans.get_finished_spans()
    assert (
        dict(span.resource.attributes).items()
        >= {
            "service.name": "oncall",
            "service.version": "1.2.3",
            "deployment.environment.name": "test",
        }.items()
    )
    assert dict(span.attributes or {}) == {SESSION_ID: "evt_1"}, "only the session is copied"


@pytest.mark.parametrize(
    ("detail", "kept"),
    [
        ("workspace", {TENANT_ID, WORKSPACE_ID}),
        ("tenant", {TENANT_ID}),
        ("none", set[str]()),
    ],
)
def test_views_apply_the_level_of_detail(detail: Any, kept: set[str], captured: Captured) -> None:
    with configure_telemetry(
        service_name="oncall", metrics_detail=detail, instrument=(), **captured.options()
    ) as handle:
        telemetry = Telemetry(meter_provider=handle.meter_provider)
        telemetry.record(
            EVENTS_PUBLISHED,
            1,
            tenant_id="t1",
            workspace_id="w1",
            attributes={EVENT_TYPE: "app:deploy.finished"},
        )
        [point] = captured.points("reflexr.events.published")
    assert set(point) == kept | {EVENT_TYPE}


def test_metric_views_cover_every_reflexr_metric() -> None:
    views = metric_views("none")
    assert all(view._meter_name == SCOPE for view in views)
    assert all(TENANT_ID not in (view._attribute_keys or ()) for view in views)


def test_a_record_logged_in_a_tenants_span_carries_its_tenant(captured: Captured) -> None:
    handle = configure_telemetry(service_name="oncall", instrument=(), **captured.options())
    tracer = handle.tracer_provider.get_tracer("test")
    log = logging.getLogger("oncall")
    with tracer.start_as_current_span("work", attributes={TENANT_ID: "acme"}):
        with tracer.start_as_current_span("query"):
            log.warning("inside")
        log.warning("given", extra={TENANT_ID: "its own"})
    with tracer.start_as_current_span("stream") as stream:
        stream.set_attribute(TENANT_ID, "globex")  # named once it is known
        log.warning("named later")
    log.warning("outside")
    assert handle.logger_provider is not None
    handle.logger_provider.force_flush()
    tenants = {
        record.log_record.body: (record.log_record.attributes or {}).get(TENANT_ID)
        for record in captured.logs.get_finished_logs()
    }
    assert tenants == {
        "inside": "acme",
        "given": "its own",
        "named later": "globex",
        "outside": None,
    }
    handle.shutdown()


def test_fastapi_apps_are_traced(handle: TelemetryHandle, captured: Captured) -> None:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> str:
        return "pong"

    handle.instrument_app(app)
    with TestClient(app) as client:
        assert client.get("/ping").json() == "pong"
    handle.tracer_provider.force_flush()
    assert [span.name for span in captured.spans.get_finished_spans()] == ["GET /ping"]


QUERY = "tenant=acme&access_token=s3cret"


def test_requests_and_websockets_are_traced_without_their_access_tokens(
    handle: TelemetryHandle, captured: Captured
) -> None:
    app = FastAPI()

    @app.get("/items")
    async def items() -> list[str]:
        return []

    @app.websocket("/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.close()

    handle.instrument_app(app)
    with TestClient(app) as client:
        client.get(f"/items?{QUERY}")
        with client.websocket_connect(f"/stream?{QUERY}"):
            pass
    handle.tracer_provider.force_flush()
    urls = [
        str(value)
        for span in captured.spans.get_finished_spans()
        for key, value in (span.attributes or {}).items()
        if key in URL_ATTRIBUTES and "access_token" in str(value)
    ]
    assert len(urls) == 2, "the request's and the WebSocket's"
    assert all("s3cret" not in url and "access_token=REDACTED" in url for url in urls), urls


async def test_sqlalchemy_engines_are_traced(
    handle: TelemetryHandle, captured: Captured, tmp_path: Any
) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    try:
        handle.instrument_engine(engine)
        handle.instrument_engine(engine.sync_engine)
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    finally:
        await engine.dispose()
    handle.tracer_provider.force_flush()
    names = [span.name for span in captured.spans.get_finished_spans()]
    assert any(name.startswith("select") or name == "SELECT" for name in names), names
