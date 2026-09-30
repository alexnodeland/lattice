"""An idle application exports no spans: subscriptions and mirrors poll storage untraced.

SQL storage polls the log for other processes' commits. With the SQLAlchemy instrumentation on,
each poll's query used to be a trace of its own; now polls are untraced, and only the work they
find is traced, where it happens (ADR-0046).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from pathlib import Path

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from artifactr.core import Envelope, GiveFeedback, ThreadTarget, UserActor
from artifactr.otel import TelemetryHandle, configure_telemetry
from artifactr.scores import FeedbackMirror
from artifactr.sql import SqlStorage, create_schema, create_sqlite_engine
from artifactr.telemetry import untraced
from artifactr.workspace import Workspace, Workspaces
from evalr.memory import InMemoryScoreSink

POLL = timedelta(milliseconds=5)
CURSOR = "langfuse"


class App:
    """A workspace on SQLite, with telemetry, a subscriber and a feedback mirror running."""

    def __init__(
        self,
        telemetry: TelemetryHandle,
        ws: Workspace,
        exported: InMemorySpanExporter,
        reader: InMemoryMetricReader,
    ) -> None:
        self.telemetry = telemetry
        self.ws = ws
        self.exported = exported
        self.reader = reader
        self.received: list[Envelope] = []
        self.scores = InMemoryScoreSink()
        self.tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        self.tasks = [
            asyncio.create_task(self.subscribe()),
            asyncio.create_task(FeedbackMirror(self.ws, self.scores, cursor=CURSOR).follow()),
        ]

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def subscribe(self) -> None:
        async for envelope in self.ws.subscribe():
            self.received.append(envelope)

    def spans(self) -> list[ReadableSpan]:
        self.telemetry.tracer_provider.force_flush()
        return list(self.exported.get_finished_spans())

    def pool(self) -> dict[str, float]:
        """The SQLAlchemy instrumentation's connection pool metric, by state."""
        data = self.reader.get_metrics_data()
        return {
            str(dict(point.attributes or {})["state"]): point.value
            for resource in (data.resource_metrics if data else ())
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == "db.client.connections.usage"
            for point in metric.data.data_points
            if isinstance(point, NumberDataPoint)
        }


async def eventually(condition: Callable[[], Awaitable[bool]]) -> None:
    for _ in range(200):
        if await condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("never happened")


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[App]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'app.db'}"
    setup = create_sqlite_engine(url)
    await create_schema(setup)
    await setup.dispose()
    # A fresh engine, whose first connection a poll opens: the pool's metrics must still count it.
    engine = create_sqlite_engine(url)
    exported, reader = InMemorySpanExporter(), InMemoryMetricReader()
    telemetry = configure_telemetry(
        service_name="app",
        instrument=("sqlalchemy",),
        engines=[engine],
        logs=False,
        set_global=False,
        span_exporter=exported,
        metric_reader=reader,
    )
    workspaces = Workspaces(
        SqlStorage(engine, poll_interval=POLL),
        tracer_provider=telemetry.tracer_provider,
        meter_provider=telemetry.meter_provider,
    )
    ws = await workspaces.open("acme", "launch", actor=UserActor(id="alice"))
    app = App(telemetry, ws, exported, reader)
    app.start()
    try:
        yield app
    finally:
        await app.stop()
        telemetry.shutdown()
        await engine.dispose()


async def test_an_idle_application_exports_no_spans(app: App) -> None:
    await asyncio.sleep(20 * POLL.total_seconds())
    assert app.spans() == [], "no trace per poll"
    pool = app.pool()
    assert sum(pool.values()) == 1, f"the pool's one connection, which a poll opened: {pool}"


async def test_the_work_a_poll_finds_is_traced_where_it_happens(app: App) -> None:
    tracer = app.telemetry.tracer_provider.get_tracer("app")
    with tracer.start_as_current_span("POST /commands") as request:
        thread = await app.ws.create_thread("Launch")
        target = ThreadTarget(thread_id=thread.id)
        await app.ws.commit(
            GiveFeedback(feedback_type="helpfulness", target=target, value={"rating": 5})
        )
        head = await app.ws.head_seq()

    async def received() -> bool:
        return len(app.received) == head

    async def scored() -> bool:
        return bool(app.scores.scores)

    await eventually(received)
    await eventually(scored)

    async def saved() -> bool:
        with untraced():  # the test's own look, not the application's work
            return await app.ws.cursor(CURSOR) == head

    await eventually(saved)
    await asyncio.sleep(10 * POLL.total_seconds())
    spans = app.spans()
    traces = {span.context.trace_id for span in spans if span.context}
    assert traces == {request.get_span_context().trace_id}, (
        "every span is in the request's trace: the subscriber's and the mirror's queries, and "
        "the polls', make none"
    )
    names = [span.name for span in spans]
    assert "artifactr.commit create_thread" in names
    assert "artifactr.commit give_feedback" in names
    scopes = {span.instrumentation_scope.name for span in spans if span.instrumentation_scope}
    assert "opentelemetry.instrumentation.sqlalchemy" in scopes, "the commits' queries are traced"
