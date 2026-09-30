"""Whole traces in Langfuse, and each turn's session, user, tags and metadata."""

from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import CreateThread, ExternalAgentActor, SetFocus, UserActor
from artifactr.langfuse import MAX_ATTRIBUTE, langfuse_turn, should_export_span, turn_attributes
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.agent.conftest import Gate, Script, say, started
from tests.artifact_types import Note
from tests.langfuse.conftest import Backend

ALICE = UserActor(id="alice")


def test_whole_traces_are_exported(backend: Backend) -> None:
    for scope in (
        "artifactr",
        "opentelemetry.instrumentation.sqlalchemy",
        "opentelemetry.instrumentation.fastapi",
        "mcp-python-sdk",
        "pydantic-ai",
        "some.library",
    ):
        with backend.tracer_provider.get_tracer(scope).start_as_current_span(scope):
            pass
    with backend.tracer_provider.get_tracer("other.llm").start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
    assert backend.exported() == [
        "artifactr",
        "opentelemetry.instrumentation.sqlalchemy",
        "opentelemetry.instrumentation.fastapi",
        "mcp-python-sdk",
        "pydantic-ai",
        "chat",
    ]


def test_a_span_without_a_scope_follows_langfuses_default() -> None:
    assert not should_export_span(ReadableSpan(name="anonymous"))


async def test_a_turn_carries_its_session_user_tags_and_metadata(backend: Backend) -> None:
    providers: dict[str, Any] = {"tracer_provider": backend.tracer_provider}
    ws = await Workspaces(InMemoryStorage(), **providers).open("acme", "launch", actor=ALICE)
    thread = await ws.create_thread("Launch")
    await ws.create(Note(text="Ship"), artifact_id="n1")
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("n1",)))
    agent: Agent[Session[Gate], Any] = Agent(
        Script(say("Hello.")).model,
        deps_type=Session[Gate],
        capabilities=[
            ArtifactWorkspace(types=[Note]),
            Instrumentation(settings=InstrumentationSettings(**providers)),
        ],
    )
    runner = Runner(agent, app=Gate(), turn_context=langfuse_turn, **providers)
    handle = started(await runner.send(ws, thread.id, "Hi"))
    await handle.wait()
    backend.exported()
    spans = {span.name: dict(span.attributes or {}) for span in backend.spans.get_finished_spans()}
    turn, run = spans["invoke_workflow turn"], spans["invoke_agent agent"]
    for attributes in (turn, run):
        assert attributes["session.id"] == thread.id
        assert attributes["user.id"] == "alice"
        assert attributes["langfuse.trace.name"] == "turn"
        assert attributes["langfuse.trace.tags"] == ("tenant:acme", "workspace:launch", "kind:note")
        assert attributes["langfuse.trace.metadata.run_id"] == handle.run_id
        assert attributes["langfuse.trace.metadata.trigger"] == "message"


async def test_attributes_are_ascii_and_within_langfuses_limits() -> None:
    client = ExternalAgentActor(client_id="claude-code")
    ws = await Workspaces(InMemoryStorage()).open("acme", "launch", actor=client)
    thread_id = "thr_é" + "x" * 300
    await ws.commit(CreateThread(thread_id=thread_id))
    session = Session[None].start(ws, thread_id, app=None, requested_by=client)
    attributes = await turn_attributes(session)
    assert attributes["session_id"] == ("thr_?" + "x" * 300)[:MAX_ATTRIBUTE]
    assert attributes["user_id"] is None, "only people are users"
    assert attributes["tags"] == ["tenant:acme", "workspace:launch"]
