"""The feedback mirror records through evalr's Langfuse score sink."""

from evalr.langfuse import LangfuseScoreSink
from opentelemetry.sdk.trace import TracerProvider

from artifactr.core import AgentActor, GiveFeedback, RunStarted, TurnTarget, UserActor
from artifactr.scores import FeedbackMirror
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.langfuse.conftest import Backend

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"


async def test_feedback_reaches_langfuse_on_its_trace(backend: Backend) -> None:
    workspaces = Workspaces(InMemoryStorage(), tracer_provider=TracerProvider())
    ws = await workspaces.open("acme", "launch", actor=UserActor(id="alice"))
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_1"))
    await agent.record(RunStarted(run_id="run_1", thread_id=thread.id, trace_id=TRACE))
    await ws.commit(
        GiveFeedback(
            feedback_type="helpfulness", target=TurnTarget(run_id="run_1"), value={"rating": 5}
        )
    )
    sink = LangfuseScoreSink(backend.client)
    mirror = FeedbackMirror(ws, sink, cursor="langfuse")
    [envelope] = await ws.read(last=1)
    [sent] = await mirror.mirror(envelope)
    await sink.flush()
    body = backend.api.scores[sent.id]
    assert (body["name"], body["value"], body["traceId"]) == ("helpfulness.rating", 5.0, TRACE)
    assert body["metadata"]["actor"] == "user:alice"
    assert "observationId" not in body, "the mirror names no span"
