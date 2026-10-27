"""Exact usage: what each model request used, live as it ends and with the run's end (ADR-0096)."""

import asyncio

import pytest
from pydantic_ai import FunctionToolset, RunContext

from artifactr.agent import FanoutChannel, Runner, Session, StepUsed, to_live
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
    make_runner,
    say,
    started,
)


async def _watched(runner: Runner[Gate], run_id: RunId) -> list[LiveFrame]:
    return [frame async for frame in runner.watch(run_id)]


async def test_each_request_sends_its_usage_and_the_runs_so_far(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold"), say("Done.")), tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Go"))
    watcher = asyncio.create_task(_watched(runner, handle.run_id))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    gate.release.set()
    await handle.wait()
    frames = await asyncio.wait_for(watcher, timeout=2)
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
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold")), tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Go"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    assert await runner.stop(handle.run_id)
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.status == "stopped"
    assert ended.usage is not None
    assert (ended.usage.requests, len(ended.usage.steps)) == (1, 1)
    assert ended.usage.model == ended.usage.steps[0].model


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


def _usage(requests: int) -> LiveFrame:
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
    await channel.send(_usage(1))
    for n in range(3):
        await channel.send(_text(n))
    assert await _first(channel, 2) == [_text(2), _usage(1)], "a total: its place is no matter"


async def test_a_count_still_buffered_is_sent_once() -> None:
    channel = FanoutChannel(buffer=4)
    await channel.send(_text(0))
    await channel.send(_usage(1))
    await channel.send(_text(1))
    assert await _first(channel, 3) == [_text(0), _usage(1), _text(1)]
    channel.close("r1")
    assert [frame async for frame in channel.watch("r1")] == []
