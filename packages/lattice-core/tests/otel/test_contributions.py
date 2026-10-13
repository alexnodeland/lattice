"""Contributions: each library's views, span filter and advice, one per library."""

import json
import uuid
from dataclasses import replace
from typing import Any

import httpx
import pytest
from langfuse import propagate_attributes
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lattice_core.otel.configure import TelemetryHandle, configure_telemetry
from lattice_core.otel.contribution import Contribution
from tests.otel.conftest import DEMO, KIND, REQUESTS, SIBLING, TENANT, WORKSPACE, Captured

QUIET: dict[str, Any] = {"instrument": (), "logs": False, "set_global": False}


def test_every_librarys_views_apply_the_level_of_detail(captured: Captured) -> None:
    with configure_telemetry(
        DEMO, SIBLING, service_name="app", metrics_detail="tenant", **captured.options()
    ) as handle:
        scoped = {TENANT: "t1", WORKSPACE: "w1"}
        requests = handle.meter_provider.get_meter("demo").create_counter(REQUESTS)
        requests.add(1, {**scoped, KIND: "read"})
        firings = handle.meter_provider.get_meter("sibling").create_counter("sibling.firings")
        firings.add(1, {**scoped, "rule": "page"})
        [demos] = captured.points(REQUESTS)
        [siblings] = captured.points("sibling.firings")
    assert set(demos) == {TENANT, KIND}, "the first library's views are kept"
    assert set(siblings) == {TENANT, "rule"}, "the sibling's views are applied too"


def test_one_contribution_per_library_the_first_given() -> None:
    mine = Contribution(
        name="demo",
        metric_views=lambda detail: [],
        should_export_span=lambda span: False,
        instrument=frozenset(),
    )
    reader = InMemoryMetricReader()
    with configure_telemetry(
        mine,
        DEMO,
        SIBLING,
        replace(SIBLING, instrument=frozenset({"asyncpg"})),
        service_name="app",
        metrics_detail="none",
        span_exporter=InMemorySpanExporter(),
        metric_reader=reader,
        logs=False,
        set_global=False,
    ) as handle:
        requests = handle.meter_provider.get_meter("demo").create_counter(REQUESTS)
        requests.add(1, {TENANT: "t1", KIND: "read"})
        assert not AsyncPGInstrumentor().is_instrumented_by_opentelemetry, "the second sibling"
        assert SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry, "the first sibling"
    data = reader.get_metrics_data()
    assert data is not None
    [point] = [
        dict(p.attributes or {})
        for r in data.resource_metrics
        for s in r.scope_metrics
        for m in s.metrics
        for p in m.data.data_points
    ]
    assert TENANT in point, "the library's views were replaced by the application's own, none"


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


def test_the_contributions_advice_chooses_the_instrumentations() -> None:
    with telemetry_with(DEMO):
        assert SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry
        assert not AsyncPGInstrumentor().is_instrumented_by_opentelemetry, (
            "SQLAlchemy's spans already cover the queries asyncpg runs"
        )
    advising = replace(SIBLING, instrument=frozenset({"asyncpg"}))
    with telemetry_with(DEMO, advising):
        assert AsyncPGInstrumentor().is_instrumented_by_opentelemetry
    with telemetry_with(DEMO, advising, instrument=("fastapi",)):
        assert not AsyncPGInstrumentor().is_instrumented_by_opentelemetry, "told which"
        assert not SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry


class FakeLangfuseApi:
    """The part of Langfuse's HTTP API a client sends scores to, in memory."""

    def __init__(self) -> None:
        self.scores: dict[str, dict[str, Any]] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/public/ingestion":
            for event in json.loads(request.content)["batch"]:
                if event["type"] == "score-create":
                    self.scores[event["body"]["id"]] = event["body"]
            return httpx.Response(207, json={"successes": [], "errors": []})
        return httpx.Response(404)


class Langfuse:
    """configure_telemetry's options for a Langfuse client on an in-process Langfuse API."""

    def __init__(self) -> None:
        self.api = FakeLangfuseApi()
        self.spans = InMemorySpanExporter()

    def options(self) -> dict[str, Any]:
        return {
            "public_key": f"pk-lf-{uuid.uuid4()}",  # Langfuse shares resources by public key
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
        with propagate_attributes(session_id="thr_1"), tracer.start_as_current_span(scope):
            pass
    with handle.tracer_provider.get_tracer("other.llm").start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
    handle.tracer_provider.force_flush()
    assert handle.langfuse is not None
    handle.langfuse.flush()


def test_langfuse_keeps_a_span_any_library_keeps(langfuse: Langfuse) -> None:
    collector = InMemorySpanExporter()
    with configure_telemetry(
        DEMO,
        SIBLING,
        service_name="app",
        span_exporter=collector,
        metric_reader=InMemoryMetricReader(),
        langfuse="traces",
        langfuse_options=langfuse.options(),
        **QUIET,
    ) as handle:
        spans_from(handle, "demo", "sibling", "noise")
    kept = [span.name for span in langfuse.spans.get_finished_spans()]
    assert kept == ["demo", "sibling", "chat"]
    assert len(collector.get_finished_spans()) == 4, "the Collector gets every span"


def test_with_scores_langfuse_gets_no_spans_but_sessions_and_scores(langfuse: Langfuse) -> None:
    collector = InMemorySpanExporter()
    with configure_telemetry(
        DEMO,
        service_name="app",
        span_exporter=collector,
        metric_reader=InMemoryMetricReader(),
        langfuse="scores",
        langfuse_options=langfuse.options(),
        **QUIET,
    ) as handle:
        spans_from(handle, "demo")
        assert handle.langfuse is not None
        handle.langfuse.create_score(name="rating.stars", value=4.0, session_id="thr_1")
        handle.langfuse.flush()
    assert langfuse.spans.get_finished_spans() == (), "the Collector sends Langfuse the spans"
    sessions = [dict(s.attributes or {}).get("session.id") for s in collector.get_finished_spans()]
    assert "thr_1" in sessions, "the session is set on the spans the Collector sends"
    [score] = langfuse.api.scores.values()
    assert (score["name"], score["sessionId"]) == ("rating.stars", "thr_1")


def test_an_explicit_span_filter_wins(langfuse: Langfuse) -> None:
    with configure_telemetry(
        DEMO,
        service_name="app",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
        langfuse="scores",
        langfuse_options={**langfuse.options(), "should_export_span": lambda span: True},
        **QUIET,
    ) as handle:
        spans_from(handle, "noise")
    assert [span.name for span in langfuse.spans.get_finished_spans()] == ["noise", "chat"]
