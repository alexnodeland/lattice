"""Exact usage: what each model request used, live as it ends and with the run's end (ADR-0096)."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import FunctionToolset, ModelMessage, ModelResponse, RunContext, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage as PydanticUsage

from artifactr.agent import FanoutChannel, Runner, Session, StepUsed, function_model, to_live
from artifactr.agent.capability import _usage
from artifactr.core import (
    LiveFrame,
    RunEnded,
    RunId,
    RunUsage,
    StepUsage,
    TextDelta,
    Thread,
    UsageUpdate,
)
from artifactr.workspace import Workspace
from tests.agent.conftest import (
    Gate,
    MakeRunner,
    Script,
    call,
    event_as,
    make_agent,
    say,
    started,
)


async def _watched(runner: Runner[Gate], run_id: RunId) -> list[LiveFrame]:
    return [frame async for frame in runner.watch(run_id)]


async def test_each_request_sends_its_usage_and_the_runs_so_far(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    app_tools: FunctionToolset[Session[Gate]],
    runners: MakeRunner,
) -> None:
    runner = runners(make_agent(Script(call("hold"), say("Done.")), tools=[app_tools]))
    handle = started(await runner.send(ws, thread.id, "Go"))
    watcher = asyncio.create_task(_watched(runner, handle.run_id))
    try:
        await asyncio.wait_for(gate.entered.wait(), timeout=2)
        gate.release.set()
        await handle.wait()
        frames = await asyncio.wait_for(watcher, timeout=2)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
    updates = [f.event for f in frames if isinstance(f.event, UsageUpdate)]
    assert [(u.step, u.exact, u.total.requests) for u in updates] == [(0, True, 1), (1, True, 2)]
    first, second = (u.usage for u in updates)
    assert first.model is not None
    assert first.model.startswith("function:"), "the model that answered, as it names itself"
    assert updates[1].total == RunUsage(
        requests=2,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        model=second.model,
    ), "the run's whole count so far, not an increment"
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.usage == updates[1].total.model_copy(update={"steps": (first, second)})
    assert all(step.duration_ms is not None and step.duration_ms >= 0 for step in (first, second))


async def test_a_stopped_run_records_the_steps_it_took(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    app_tools: FunctionToolset[Session[Gate]],
    runners: MakeRunner,
) -> None:
    runner = runners(make_agent(Script(call("hold")), tools=[app_tools]))
    handle = started(await runner.send(ws, thread.id, "Go"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    assert await runner.stop(handle.run_id)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.status == "stopped"
    assert ended.usage is not None
    assert (ended.usage.requests, len(ended.usage.steps)) == (1, 1)
    assert ended.usage.model == ended.usage.steps[0].model


async def test_a_run_stopped_mid_request_records_no_step_for_it(
    ws: Workspace, thread: Thread, gate: Gate, runners: MakeRunner
) -> None:
    async def held(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await gate.wait()
        return ModelResponse(parts=[TextPart("never")])

    agent = make_agent(Script())
    runner = runners(agent)
    with agent.override(model=function_model(held)):
        handle = started(await runner.send(ws, thread.id, "Go"))
        await asyncio.wait_for(gate.entered.wait(), timeout=2)
        assert await runner.stop(handle.run_id)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.usage is not None
    assert ended.usage == RunUsage(), (
        "a request stopped before its response ended is no step, and pydantic-ai counted none of it"
    )


async def test_a_run_stopped_after_some_streamed_text_counts_it_in_a_last_step(
    ws: Workspace, thread: Thread, gate: Gate, runners: MakeRunner
) -> None:
    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        yield "Half an answer, "
        await gate.wait()
        yield "never sent"

    agent = make_agent(Script())
    runner = runners(agent)
    with agent.override(model=FunctionModel(stream_function=stream)):
        handle = started(await runner.send(ws, thread.id, "Go"))
        await asyncio.wait_for(gate.entered.wait(), timeout=2)
        assert await runner.stop(handle.run_id)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.status == "stopped"
    assert ended.usage is not None
    [step] = ended.usage.steps
    assert step.output_tokens > 0, "the tokens streamed before the stop are counted"
    assert (step.model, step.duration_ms) == (None, None), "in a step no response ended"
    assert (ended.usage.requests, ended.usage.output_tokens) == (1, step.output_tokens)


def test_a_run_ended_early_counts_what_no_step_saw_and_its_sums_are_the_steps() -> None:
    # One step's cache write is first-class, the other's a detail, as LiteLLM gives Anthropic's.
    steps = [
        StepUsage(model="a", input_tokens=10, cache_write_tokens=4),
        StepUsage(model="b", input_tokens=20, cache_write_tokens=6),
    ]
    counted = PydanticUsage(requests=2, input_tokens=35, output_tokens=2, cache_write_tokens=4)
    counted.details["cache_creation_input_tokens"] = 6
    whole = _usage(counted, steps)
    assert (whole.input_tokens, whole.cache_write_tokens, whole.model) == (30, 10, "b")
    early = _usage(counted, steps, partial=True)
    assert early.steps[-1] == StepUsage(input_tokens=5, output_tokens=2)
    assert (early.requests, early.input_tokens, early.output_tokens) == (2, 35, 2)
    assert early.model == "b", "the last step that names a model"
    assert _usage(counted, ()).cache_write_tokens == 4, "no steps: pydantic-ai's sums"


async def test_a_failed_run_records_the_steps_it_took(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def boom(ctx: RunContext[Session[Gate]]) -> str:
        """Fail."""
        raise RuntimeError("the disk is full")

    handle = started(
        await runners(make_agent(Script(call("boom")), tools=[tools])).send(ws, thread.id, "Go")
    )
    with pytest.raises(RuntimeError, match="disk"):
        await handle.wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.status == "failed"
    assert ended.usage is not None
    assert (ended.usage.requests, len(ended.usage.steps)) == (1, 1)


def test_a_step_used_is_a_usage_frame() -> None:
    step = StepUsage(model="m", input_tokens=3)
    total = RunUsage(requests=1, input_tokens=3, model="m")
    assert to_live(StepUsed(step=0, usage=step, total=total)) == [
        UsageUpdate(step=0, usage=step, total=total)
    ]
    frame = LiveFrame(run_id="r1", event=UsageUpdate(step=0, usage=step, total=total))
    assert LiveFrame.model_validate_json(frame.model_dump_json()) == frame


def _count(requests: int) -> LiveFrame:
    total = RunUsage(requests=requests)
    return LiveFrame(run_id="r1", event=UsageUpdate(step=0, usage=StepUsage(), total=total))


def _text(n: int) -> LiveFrame:
    return LiveFrame(run_id="r1", event=TextDelta(part=0, delta=str(n)))


async def _first(channel: FanoutChannel, count: int) -> list[LiveFrame]:
    frames: list[LiveFrame] = []
    async for frame in channel.watch("r1"):
        frames.append(frame)
        if len(frames) == count:
            break
    return frames


async def test_a_late_watcher_learns_the_count_that_left_the_buffer() -> None:
    channel = FanoutChannel(buffer=2)
    await channel.send(_count(1))
    for n in range(3):
        await channel.send(_text(n))
    assert await _first(channel, 2) == [_text(2), _count(1)], "a total: its place is no matter"


async def test_a_count_still_buffered_is_sent_once() -> None:
    channel = FanoutChannel(buffer=4)
    await channel.send(_text(0))
    await channel.send(_count(1))
    await channel.send(_text(1))
    assert await _first(channel, 3) == [_text(0), _count(1), _text(1)]
    channel.close("r1")
    assert [frame async for frame in channel.watch("r1")] == []
