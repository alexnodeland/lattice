"""A turn that waits on a model, or a tool, that sends nothing is failed, not left (ADR-0095)."""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    FunctionToolset,
    ModelMessage,
    RunContext,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCalls, FunctionModel

from artifactr.agent import (
    ArtifactWorkspace,
    Liveness,
    Runner,
    Session,
    ToolStalled,
    is_local_model,
)
from artifactr.agent.liveness import watched
from artifactr.core import RunEnded, RunUsage, TextDelta, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import Gate, Script, call, event_as, make_agent, say, started
from tests.artifact_types import Checklist, Note

WAIT = 0.25
"""A wait short enough for a test, and five times what a test sleeps against it."""

QUICK = Liveness(first_output=WAIT, no_output=WAIT, tool=WAIT)


class Stalling:
    """A model that streams ``first``, then nothing, forever; it knows when its stream closed."""

    def __init__(self, *first: str) -> None:
        self.first = first
        self.closed = asyncio.Event()
        self.stalled = asyncio.Event()

    @property
    def model(self) -> FunctionModel:
        async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
            try:
                for text in self.first:
                    yield text
                self.stalled.set()
                await asyncio.Event().wait()
            finally:
                self.closed.set()

        def respond(messages: list[ModelMessage], info: AgentInfo) -> Any:
            raise AssertionError("the runner streams every request")

        return FunctionModel(respond, stream_function=stream)


def _agent(model: FunctionModel) -> Agent[Session[Gate], Any]:
    return Agent(
        model,
        deps_type=Session[Gate],
        capabilities=[ArtifactWorkspace(types=[Note, Checklist])],
    )


async def test_a_model_that_never_starts_answering_fails_the_run_as_stalled(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    stalling = Stalling()
    runner = Runner(_agent(stalling.model), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Hello?"))
    with pytest.raises(Exception, match=r"didn't start answering within 0.25 seconds"):
        await asyncio.wait_for(handle.wait(), timeout=2)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "model_stalled")
    assert ended.error == (
        "the model (function:respond:stream) didn't start answering within 0.25 seconds"
    )
    assert ended.usage == RunUsage(), "what it used so far: nothing"
    assert stalling.closed.is_set(), "the request was torn down"
    await runner.drain()
    assert runner.running(thread.id) is None, "the thread is released"
    again = Runner(make_agent(Script(say("Here now."))), app=gate)
    handle = started(await again.send(ws, thread.id, "Hello?"))
    assert (await handle.wait()).output == "Here now.", "and the next message runs"


async def test_a_model_that_stops_mid_reply_fails_the_run_and_keeps_what_it_sent(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    stalling = Stalling("Here is the ", "plan: ")
    runner = Runner(_agent(stalling.model), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Plan it"))
    frames = [frame async for frame in runner.watch(handle.run_id)]
    with pytest.raises(Exception, match=r"stopped answering within 0.25 seconds"):
        await handle.wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "model_stalled")
    assert ended.usage is not None, "what it used so far"
    assert stalling.closed.is_set()
    deltas = [f.event for f in frames if isinstance(f.event, TextDelta)]
    assert deltas == [TextDelta(part=0, delta="Here is the plan: ", offset=0)], (
        "sent before the end"
    )


async def test_a_run_stopped_while_its_model_stalls_is_stopped_not_failed(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    stalling = Stalling("Here is")
    runner = Runner(_agent(stalling.model), app=gate, liveness=Liveness(no_output=10.0))
    handle = started(await runner.send(ws, thread.id, "Plan it"))
    await stalling.stalled.wait()
    assert await runner.stop(handle.run_id)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.status == "stopped"
    assert stalling.closed.is_set()


def _slow_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def hold(ctx: RunContext[Session[Gate]]) -> str:
        """Wait until the test releases the gate."""
        await ctx.deps.app.wait()
        return "released"

    @tools.tool
    async def quick(ctx: RunContext[Session[Gate]]) -> str:
        """Return at once."""
        return "done"

    return tools


async def test_a_tool_that_never_returns_fails_the_run_as_stalled(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("hold"), say("Done."))
    runner = Runner(make_agent(script, tools=[_slow_tools()]), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Go"))
    with pytest.raises(Exception, match=r"the tool hold didn't return within 0.25 seconds"):
        await asyncio.wait_for(handle.wait(), timeout=2)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "tool_stalled")
    assert ended.usage is not None
    assert ended.usage.requests == 1, "what it used so far"
    assert len(script.requests) == 1, "the model was not asked again"


async def test_the_stalled_tool_is_named_among_the_calls_still_running() -> None:
    """The handler's stream, as pydantic-ai gives it for a round of tool calls: each call's
    event as it starts, each result as it returns; a result that never comes is the stall."""

    async def events() -> AsyncIterator[Any]:
        yield FunctionToolCallEvent(part=ToolCallPart(tool_name="hold", tool_call_id="c1"))
        yield FunctionToolCallEvent(part=ToolCallPart(tool_name="quick", tool_call_id="c2"))
        yield FunctionToolResultEvent(
            part=ToolReturnPart(tool_name="quick", content="done", tool_call_id="c2")
        )
        await asyncio.Event().wait()

    seen = 0

    async def handler(ctx: Any, stream: AsyncIterable[Any]) -> None:
        nonlocal seen
        async for _ in stream:  # each counted as it comes, before the stream fails
            seen += 1

    ctx: Any = SimpleNamespace(model=SimpleNamespace(model_name="default"))
    timed = watched(handler, Liveness(first_output=WAIT, no_output=WAIT, tool=WAIT))
    with pytest.raises(ToolStalled, match=r"the tool hold didn't return within 0.25 seconds"):
        await timed(ctx, events())
    assert seen == 3, "every event reached the handler first"


async def test_a_slow_tool_is_not_a_stalled_model(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    patient = Liveness(first_output=WAIT, no_output=WAIT, tool=None)
    script = Script(call("hold"), say("Done."))
    runner = Runner(make_agent(script, tools=[_slow_tools()]), app=gate, liveness=patient)
    handle = started(await runner.send(ws, thread.id, "Go"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    await asyncio.sleep(2 * WAIT)  # past the model's wait: the tool's is the one that counts
    gate.release.set()
    assert (await asyncio.wait_for(handle.wait(), timeout=2)).output == "Done."


async def test_a_reply_that_keeps_coming_slowly_is_waited_for(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    """Each event restarts the wait: a reply that keeps coming is never a stall."""

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        for word in ("one ", "two ", "three ", "four "):
            await asyncio.sleep(WAIT / 5)
            yield word

    model = FunctionModel(lambda messages, info: say("unused"), stream_function=stream)
    runner = Runner(_agent(model), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Count"))
    assert (await asyncio.wait_for(handle.wait(), timeout=2)).output == "one two three four "


async def test_a_reply_that_ends_is_not_failed_once_the_wait_has_passed(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    runner = Runner(make_agent(Script(say("Done."))), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Go"))
    assert (await handle.wait()).output == "Done."
    await asyncio.sleep(2 * WAIT)  # no wait is left running past the reply
    assert (await ws.run(handle.run_id)).status == "completed"


def test_a_local_model_is_known_by_its_name_and_the_application_has_the_last_word() -> None:
    assert is_local_model("ollama/llama3")
    assert is_local_model("lm_studio/qwen")
    assert is_local_model("local")
    assert is_local_model("local-fast")
    assert not is_local_model("default")
    assert not is_local_model("anthropic/claude-sonnet")
    assert not is_local_model("unknown-thing"), "unknown is hosted"
    assert is_local_model("default", local={"default"})
    assert not is_local_model("ollama/llama3", hosted={"ollama/llama3"})
    assert not is_local_model("x", local={"x"}, hosted={"x"}), "hosted wins"


def test_the_local_limits_apply_to_local_models() -> None:
    liveness = Liveness(local_models=frozenset({"default"}))
    assert liveness.limits("default") == (300.0, 300.0)
    assert liveness.limits("fast") == (120.0, 120.0)
    assert liveness.limits("ollama/x") == (300.0, 300.0)
