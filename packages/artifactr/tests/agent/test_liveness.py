"""A turn that waits on a model, or a tool, that sends nothing is failed, not left (ADR-0095)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import Agent, FunctionToolset, ModelMessage, RunContext
from pydantic_ai.models.function import AgentInfo, DeltaToolCalls, FunctionModel

from artifactr.agent import ArtifactWorkspace, Liveness, Runner, Session, is_local_model
from artifactr.core import RunEnded, RunUsage, TextDelta, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import Gate, Script, call, event_as, make_agent, say, started
from tests.artifact_types import Checklist, Note

QUICK = Liveness(first_output=0.1, no_output=0.1, tool=0.1)
"""Waits short enough for a test: a tenth of a second each."""


def _stalling(*first: str) -> FunctionModel:
    """A model that streams ``first``, then nothing, forever."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        for text in first:
            yield text
        await asyncio.Event().wait()

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
    runner = Runner(_agent(_stalling()), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Hello?"))
    with pytest.raises(Exception, match=r"didn't start answering within 0.1 seconds"):
        await asyncio.wait_for(handle.wait(), timeout=2)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "model_stalled")
    assert ended.error == (
        "the model (function:respond:stream) didn't start answering within 0.1 seconds"
    )
    assert ended.usage == RunUsage(), "what it used so far: nothing"
    await runner.drain()
    assert runner.running(thread.id) is None, "the thread is released"
    again = Runner(make_agent(Script(say("Here now."))), app=gate)
    handle = started(await again.send(ws, thread.id, "Hello?"))
    assert (await handle.wait()).output == "Here now.", "and the next message runs"


async def test_a_model_that_stops_mid_reply_fails_the_run_and_keeps_what_it_sent(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    runner = Runner(_agent(_stalling("Here is the ", "plan: ")), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Plan it"))
    frames = [frame async for frame in runner.watch(handle.run_id)]
    with pytest.raises(Exception, match=r"stopped answering within 0.1 seconds"):
        await handle.wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "model_stalled")
    deltas = [f.event for f in frames if isinstance(f.event, TextDelta)]
    assert deltas == [TextDelta(part=0, delta="Here is the plan: ", offset=0)], (
        "sent before the end"
    )


def _slow_tools(gate: Gate) -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def hold(ctx: RunContext[Session[Gate]]) -> str:
        """Wait until the test releases the gate."""
        await ctx.deps.app.wait()
        return "released"

    return tools


async def test_a_tool_that_never_returns_fails_the_run_as_stalled(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("hold"), say("Done."))
    runner = Runner(make_agent(script, tools=[_slow_tools(gate)]), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Go"))
    with pytest.raises(Exception, match=r"the tool hold didn't return within 0.1 seconds"):
        await asyncio.wait_for(handle.wait(), timeout=2)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "tool_stalled")
    assert ended.usage is not None
    assert ended.usage.requests == 1, "what it used so far"
    assert len(script.requests) == 1, "the model was not asked again"


async def test_a_slow_tool_is_not_a_stalled_model(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    patient = Liveness(first_output=0.1, no_output=0.1, tool=None)
    script = Script(call("hold"), say("Done."))
    runner = Runner(make_agent(script, tools=[_slow_tools(gate)]), app=gate, liveness=patient)
    handle = started(await runner.send(ws, thread.id, "Go"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    await asyncio.sleep(0.3)  # longer than the model's wait: the tool's is the one that counts
    gate.release.set()
    assert (await asyncio.wait_for(handle.wait(), timeout=2)).output == "Done."


async def test_a_model_streaming_a_tool_call_slowly_is_waited_for(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    """Each event restarts the wait: a reply that keeps coming is never a stall."""

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        for word in ("one ", "two ", "three ", "four "):
            await asyncio.sleep(0.06)
            yield word

    model = FunctionModel(lambda messages, info: say("unused"), stream_function=stream)
    runner = Runner(_agent(model), app=gate, liveness=QUICK)
    handle = started(await runner.send(ws, thread.id, "Count"))
    assert (await asyncio.wait_for(handle.wait(), timeout=2)).output == "one two three four "


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
