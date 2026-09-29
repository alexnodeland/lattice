"""End to end: a turn over SQL storage, with the SDK configured by configure_telemetry.

This is RFC-0002's baggage spike, in process: the session a turn places in baggage reaches the
database spans of the same trace, through the baggage span processor.
"""

from pathlib import Path
from typing import Any

from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import UserActor
from artifactr.otel import configure_telemetry
from artifactr.sql import SqlStorage, create_schema, create_sqlite_engine
from artifactr.telemetry.attributes import SESSION_ID
from artifactr.workspace import Workspaces
from tests.agent.conftest import Gate, Script, call, say, started
from tests.artifact_types import Note


async def test_the_session_reaches_the_database_spans_of_a_turn(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await create_schema(engine)
    spans = InMemorySpanExporter()
    try:
        with configure_telemetry(
            service_name="docplan",
            instrument=("sqlalchemy",),
            engines=[engine],
            span_exporter=spans,
            metric_reader=InMemoryMetricReader(),
            logs=False,
            set_global=False,
        ) as telemetry:
            providers: dict[str, Any] = {
                "tracer_provider": telemetry.tracer_provider,
                "meter_provider": telemetry.meter_provider,
            }
            workspaces = Workspaces(SqlStorage(engine), **providers)
            ws = await workspaces.open("t1", "w1", actor=UserActor(id="alice"))
            thread = await ws.create_thread("Launch")
            script = Script(call("create_artifact", kind="note", data={"text": "Hi"}), say("Done."))
            agent: Agent[Session[Gate], Any] = Agent(
                script.model,
                deps_type=Session[Gate],
                capabilities=[ArtifactWorkspace(types=[Note]), telemetry.capability()],
            )
            runner = Runner(agent, app=Gate(), **providers)
            await started(await runner.send(ws, thread.id, "Draft")).wait()
            telemetry.tracer_provider.force_flush()
    finally:
        await engine.dispose()

    finished = spans.get_finished_spans()
    [turn] = [span for span in finished if span.name == "invoke_workflow turn"]
    assert turn.context is not None
    in_turn = [
        span
        for span in finished
        if span.context is not None and span.context.trace_id == turn.context.trace_id
    ]
    database = [
        span
        for span in in_turn
        if span.instrumentation_scope is not None
        and span.instrumentation_scope.name == "opentelemetry.instrumentation.sqlalchemy"
    ]
    assert database, "the turn's storage work is traced"
    assert all((span.attributes or {}).get(SESSION_ID) == thread.id for span in database)
