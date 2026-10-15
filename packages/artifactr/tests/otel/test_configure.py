"""artifactr's configure_telemetry: its own contribution, on the setup lattice-core tests.

Only what is artifactr's is tested here, and the redaction once more end to end, since it keeps a
browser's token out of the traces.
"""

import inspect
import logging
from typing import Any

import fastapi
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from artifactr.otel import configure as artifactr_configure
from artifactr.otel import configure_telemetry, metric_views
from artifactr.telemetry import SCOPE, Telemetry
from artifactr.telemetry.attributes import COMMAND_TYPE, TENANT_ID, WORKSPACE_ID
from artifactr.telemetry.metrics import COMMANDS
from lattice_core.otel.configure import configure_telemetry as core_configure_telemetry


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
        service_name="docplan", metrics_detail=detail, instrument=(), **captured.options()
    ) as handle:
        telemetry = Telemetry(meter_provider=handle.meter_provider)
        scoped = {TENANT_ID: "t1", WORKSPACE_ID: "w1", COMMAND_TYPE: "create_thread"}
        telemetry.add(COMMANDS, 1, scoped)
        [point] = captured.points("artifactr.commands")
    assert set(point) == kept | {COMMAND_TYPE}


def test_metric_views_cover_every_artifactr_metric() -> None:
    views = metric_views("none")
    assert all(view._meter_name == SCOPE for view in views)
    assert all(TENANT_ID not in (view._attribute_keys or ()) for view in views)


def test_a_record_logged_in_a_tenants_span_carries_its_tenant(captured: Captured) -> None:
    handle = configure_telemetry(service_name="docplan", instrument=(), **captured.options())
    tracer = handle.tracer_provider.get_tracer("test")
    log = logging.getLogger("docplan")
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


QUERY = "tenant=acme&access_token=s3cret"


def test_apps_built_after_configuring_are_traced_without_their_access_tokens(
    captured: Captured,
) -> None:
    with configure_telemetry(
        service_name="docplan", instrument=("fastapi",), **captured.options()
    ) as handle:
        app = fastapi.FastAPI()  # built after configuring, so the instrumentation patched it

        @app.get("/items")
        async def items() -> list[str]:
            return []

        with TestClient(app) as client:
            client.get(f"/items?{QUERY}")
        handle.tracer_provider.force_flush()
    [span] = [s for s in captured.spans.get_finished_spans() if s.name == "GET /items"]
    assert (span.attributes or {})["url.query"] == "tenant=acme&access_token=REDACTED"


def test_it_takes_lattice_cores_parameters() -> None:
    assert inspect.signature(configure_telemetry) == inspect.signature(core_configure_telemetry)


def test_it_forwards_its_arguments_and_adds_its_own_contribution_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def record(*contributions: Any, **options: Any) -> str:
        calls.append((contributions, options))
        return "handle"

    monkeypatch.setattr(artifactr_configure, "_configure_telemetry", record)
    other = artifactr_configure.Contribution(
        name="other",
        metric_views=lambda detail: [],
        should_export_span=lambda span: False,
        instrument=frozenset(),
    )
    handle = configure_telemetry(
        other,
        service_name="app",
        set_global=False,
        langfuse="scores",
        langfuse_options={"public_key": "pk"},
    )
    [(contributions, options)] = calls
    assert (handle, contributions[0], contributions[1].name) == ("handle", other, SCOPE)
    assert (options["set_global"], options["langfuse"], options["langfuse_options"]) == (
        False,
        "scores",
        {"public_key": "pk"},
    )
