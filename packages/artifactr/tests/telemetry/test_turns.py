"""Turns are traces: the Runner's span, pydantic-ai's spans inside it, and artifactr's ids."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from opentelemetry import baggage, trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode
from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset, RunContext
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import AnswerDeferred, Thread, UserActor
from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    ARTIFACT_ID,
    ERROR_TYPE,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_OPERATION_NAME,
    GEN_AI_WORKFLOW_NAME,
    LANGFUSE_OBSERVATION_TYPE,
    RUN_ID,
    SESSION_ID,
    TENANT_ID,
    THREAD_ID,
    TURN_OUTCOME,
    TURN_TRIGGER,
    USER_ID,
    WORKSPACE_ID,
)
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import Gate, HeldStorage, Script, call, say, started
from tests.artifact_types import Checklist, Note
from tests.telemetry.conftest import Recorder, attributes, trace_id

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")


@pytest.fixture
def gate() -> Gate:
    return Gate()


@pytest.fixture
async def ws(recorder: Recorder) -> Workspace:
    return await Workspaces(InMemoryStorage(), **recorder.providers).open("t1", "w1", actor=ALICE)


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    return await ws.create_thread("Launch")


def traced(
    script: Script,
    recorder: Recorder,
    *,
    tools: Sequence[FunctionToolset[Session[Gate]]] = (),
    output_type: Any = str,
) -> Agent[Session[Gate], Any]:
    """An agent instrumented the way an application would, with the recorder's providers."""
    return Agent(
        script.model,
        deps_type=Session[Gate],
        output_type=output_type,
        toolsets=list(tools),
        capabilities=[
            ArtifactWorkspace(types=[Note, Checklist], ask=True),
            Instrumentation(settings=InstrumentationSettings(**recorder.providers)),
        ],
    )


def named(recorder: Recorder, prefix: str) -> list[ReadableSpan]:
    return [span for span in recorder.spans() if span.name.startswith(prefix)]


def parent_id(span: ReadableSpan) -> int | None:
    return span.parent.span_id if span.parent else None


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.span_id


async def test_a_turn_is_its_own_trace_linked_to_what_started_it(
    ws: Workspace, thread: Thread, recorder: Recorder, gate: Gate
) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"text": "Ship Friday"}),
        call("read_artifact", call_id="c2", artifact_id="n_unknown"),
        say("Drafted."),
    )
    runner = Runner(traced(script, recorder), app=gate, **recorder.providers)
    request_tracer = recorder.tracer_provider.get_tracer("the application")
    with request_tracer.start_as_current_span("POST /commands") as request:
        handle = started(await runner.send(ws, thread.id, "Draft a plan"))
    await handle.wait()

    turn = recorder.span("invoke_workflow turn")
    assert turn.parent is None, "a turn starts its own trace"
    assert [link.context.span_id for link in turn.links] == [request.get_span_context().span_id]
    assert attributes(turn) == {
        GEN_AI_OPERATION_NAME: "invoke_workflow",
        GEN_AI_WORKFLOW_NAME: "turn",
        LANGFUSE_OBSERVATION_TYPE: "chain",
        TURN_TRIGGER: "message",
        TURN_OUTCOME: "completed",
        TENANT_ID: "t1",
        WORKSPACE_ID: "w1",
        SESSION_ID: thread.id,
        GEN_AI_CONVERSATION_ID: thread.id,
        THREAD_ID: thread.id,
        RUN_ID: handle.run_id,
        ACTOR_KIND: "user",
        USER_ID: "alice",
    }
    posted, replied = recorder.spans("artifactr.commit post_message")
    assert parent_id(posted) == request.get_span_context().span_id, "the message is the request's"

    [agent_run] = named(recorder, "invoke_agent")
    assert parent_id(agent_run) == span_id(turn)
    assert parent_id(replied) == span_id(agent_run), "the reply is the turn's"
    run_attributes = attributes(agent_run)
    assert run_attributes[GEN_AI_CONVERSATION_ID] == thread.id, "the thread is the conversation"
    assert run_attributes[RUN_ID] == handle.run_id, "artifactr's run id, not pydantic-ai's"
    assert run_attributes["gen_ai.agent.call.id"] != handle.run_id
    assert (run_attributes[ACTOR_KIND], run_attributes[USER_ID]) == ("agent", "alice")

    created, read = named(recorder, "execute_tool")
    [artifact] = await ws.artifacts()
    assert attributes(created)[ARTIFACT_ID] == artifact.id
    assert attributes(read)[ARTIFACT_ID] == "n_unknown"
    commit = recorder.span("artifactr.commit create_artifact")
    assert parent_id(commit) == span_id(created)

    run = await ws.run(handle.run_id)
    assert run.trace_ids == (trace_id(turn),)
    [revision] = await ws.revisions(artifact.id)
    assert revision.trace_id == trace_id(turn)
    where = {TURN_TRIGGER: "message", TURN_OUTCOME: "completed", TENANT_ID: "t1"}
    assert recorder.total("artifactr.turns", where) == 1
    assert recorder.total("artifactr.turn.duration", where) == 1


async def test_a_message_carried_out_as_a_run_ends_starts_a_turn_linked_to_it(
    recorder: Recorder, gate: Gate
) -> None:
    storage = HeldStorage()
    ws = await Workspaces(storage, **recorder.providers).open("t1", "w1", actor=ALICE)
    thread = await ws.create_thread("Launch")
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = Runner(traced(script, recorder), app=gate, **recorder.providers)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await asyncio.wait_for(releasing.entered.wait(), timeout=2)
    request_tracer = recorder.tracer_provider.get_tracer("the application")
    with request_tracer.start_as_current_span("POST /commands"):
        assert (await runner.send(ws.as_actor(BOB), thread.id, "Anything else?")).run is None
    releasing.release.set()
    await first.wait()
    await runner.drain()
    following = runner.running(thread.id)
    assert following is not None
    await following.wait()

    _, turn = recorder.spans("invoke_workflow turn")
    posted = [
        span
        for span in recorder.spans("artifactr.commit post_message")
        if attributes(span)[ACTOR_KIND] == "user"
    ]
    assert [link.context.span_id for link in turn.links] == [span_id(posted[-1])]
    assert (attributes(turn)[TURN_TRIGGER], attributes(turn)[USER_ID]) == ("message", "bob")


async def test_each_attempt_of_a_paused_run_is_its_own_trace(
    ws: Workspace, thread: Thread, recorder: Recorder, gate: Gate
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), say("Monday it is."))
    agent = traced(script, recorder, output_type=[str, DeferredToolRequests])
    runner = Runner(agent, app=gate, **recorder.providers)
    handle = started(await runner.send(ws, thread.id, "Plan the launch"))
    await handle.wait()
    answer = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer="Monday")
    resumed = started(await runner.answer(ws.as_actor(BOB), answer))
    await resumed.wait()

    paused, finished = recorder.spans("invoke_workflow turn")
    assert (attributes(paused)[TURN_OUTCOME], attributes(finished)[TURN_OUTCOME]) == (
        "paused",
        "completed",
    )
    assert attributes(finished)[TURN_TRIGGER] == "resume"
    assert attributes(finished)[USER_ID] == "bob", "the person who answered"
    assert not finished.links, "the answer was not traced"
    run = await ws.run(handle.run_id)
    assert run.trace_ids == (trace_id(paused), trace_id(finished))
    assert trace_id(paused) != trace_id(finished)


async def test_the_thread_is_the_session_inside_a_turn(
    ws: Workspace, thread: Thread, recorder: Recorder, gate: Gate
) -> None:
    seen: dict[str, object] = {}
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def look(ctx: RunContext[Session[Gate]]) -> str:
        """Look around."""
        seen["baggage"] = baggage.get_baggage(SESSION_ID)
        seen["conversation"] = ctx.conversation_id
        return "looked"

    script = Script(call("look"), say("Done."))
    runner = Runner(traced(script, recorder, tools=[tools]), app=gate, **recorder.providers)
    await started(await runner.send(ws, thread.id, "Look")).wait()
    assert seen == {"baggage": thread.id, "conversation": thread.id}
    assert baggage.get_baggage(SESSION_ID) is None, "only for the turn's duration"


async def test_a_stopped_turn_and_a_failed_turn(
    ws: Workspace, thread: Thread, recorder: Recorder, gate: Gate
) -> None:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def hold(ctx: RunContext[Session[Gate]]) -> str:
        """Wait for the gate."""
        await ctx.deps.app.wait()
        return "released"

    @tools.tool
    async def broken(ctx: RunContext[Session[Gate]]) -> str:
        """Fail."""
        raise ValueError("disk full")

    script = Script(call("hold"), call("broken"))
    runner = Runner(traced(script, recorder, tools=[tools]), app=gate, **recorder.providers)
    held = started(await runner.send(ws, thread.id, "Hold"))
    await gate.entered.wait()
    assert await runner.stop(held.run_id)
    with pytest.raises(asyncio.CancelledError):
        await held.wait()
    failing = started(await runner.send(ws, thread.id, "Break"))
    with pytest.raises(ValueError, match="disk full"):
        await failing.wait()

    stopped, failed = recorder.spans("invoke_workflow turn")
    assert attributes(stopped)[TURN_OUTCOME] == "stopped"
    assert stopped.status.status_code == StatusCode.UNSET, "stopping is not an error"
    assert (attributes(failed)[TURN_OUTCOME], attributes(failed)[ERROR_TYPE]) == (
        "failed",
        "ValueError",
    )
    assert failed.status.status_code == StatusCode.ERROR
    assert recorder.total("artifactr.turns", {TURN_OUTCOME: "stopped"}) == 1
    assert recorder.total("artifactr.turns", {TURN_OUTCOME: "failed"}) == 1


async def test_a_turn_context_is_entered_inside_the_turns_span(
    ws: Workspace, thread: Thread, recorder: Recorder, gate: Gate
) -> None:
    entered: list[tuple[str, str]] = []

    @contextlib.asynccontextmanager
    async def attribute(session: Session[Any]) -> AsyncIterator[None]:
        span = trace.get_current_span()
        entered.append((getattr(span, "name", ""), session.thread_id))
        yield

    script = Script(say("Hello."))
    runner = Runner(
        traced(script, recorder), app=gate, turn_context=attribute, **recorder.providers
    )
    await started(await runner.send(ws, thread.id, "Hi")).wait()
    assert entered == [("invoke_workflow turn", thread.id)]
