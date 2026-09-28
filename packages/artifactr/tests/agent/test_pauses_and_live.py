"""Pausing for people, stopping runs, and live output."""

import asyncio
from dataclasses import dataclass

import pytest
from pydantic_ai import (
    DeferredToolRequests,
    FunctionToolset,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    RunContext,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.messages import CustomEvent, FinalResultEvent

from artifactr.agent import ArtifactDraft, FanoutChannel, NullChannel, Session, to_live
from artifactr.core import (
    AnswerDeferred,
    AppLive,
    Draft,
    LiveFrame,
    PartEnded,
    PartStarted,
    RunEnded,
    StopRun,
    TextDelta,
    ThinkingDelta,
    Thread,
    ToolArgsDelta,
)
from artifactr.workspace import Workspace
from tests.agent.conftest import Gate, Script, call, event_as, make_agent, make_runner, say, started

ASKING = [str, DeferredToolRequests]


def _approval_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool(requires_approval=True)
    async def publish(ctx: RunContext[Session[Gate]], channel: str) -> str:
        """Publish the plan."""
        return f"published to {channel}"

    return tools


async def test_a_question_pauses_the_run_until_answered(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), say("Monday it is."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Plan the launch")).run
    assert handle is not None
    paused = await handle.wait()
    assert isinstance(paused.output, DeferredToolRequests)
    run = await ws.run(handle.run_id)
    assert (run.status, [r.tool_call_id for r in run.pending]) == ("paused", ["q1"])
    resumed = (
        await runner.answer(ws, AnswerDeferred(run_id=run.id, tool_call_id="q1", answer="Monday"))
    ).run
    assert resumed is not None
    assert resumed.run_id == handle.run_id
    assert (await resumed.wait()).output == "Monday it is."
    assert (await ws.run(run.id)).status == "completed"
    assert script.tool_returns(1) == ["Monday"]


async def test_a_chat_message_answers_a_paused_run(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), say("Monday then."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Plan it")).run
    assert handle is not None
    await handle.wait()
    resumed = (await runner.send(ws, thread.id, "Monday")).run
    assert resumed is not None
    await resumed.wait()
    assert script.tool_returns(1) == ["Monday"]


async def test_approvals_resume_the_approved_call(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("publish", call_id="a1", channel="blog"), say("Published."))
    runner = make_runner(make_agent(script, tools=[_approval_tools()], output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Publish it")).run
    assert handle is not None
    await handle.wait()
    [request] = (await ws.run(handle.run_id)).pending
    assert (request.kind, request.args) == ("approval", {"channel": "blog"})
    command = AnswerDeferred(run_id=handle.run_id, tool_call_id="a1", approved=True)
    resumed = (await runner.answer(ws, command)).run
    assert resumed is not None
    await resumed.wait()
    assert script.tool_returns(1) == ["published to blog"]


async def test_a_chat_message_declines_a_pending_approval(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("publish", call_id="a1", channel="blog"), say("Understood."))
    runner = make_runner(make_agent(script, tools=[_approval_tools()], output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Publish it")).run
    assert handle is not None
    await handle.wait()
    resumed = (await runner.send(ws, thread.id, "Not yet, wait for legal")).run
    assert resumed is not None
    await resumed.wait()
    [denied] = script.tool_returns(1)
    assert "Not yet, wait for legal" in denied


async def test_a_run_waits_for_every_answer(ws: Workspace, thread: Thread, gate: Gate) -> None:
    both = Script(
        lambda _: call("ask_user", call_id="q1", question="Day?").__class__(
            parts=[
                *call("ask_user", call_id="q1", question="Day?").parts,
                *call("publish", call_id="a1", channel="blog").parts,
            ]
        ),
        say("All set."),
    )
    runner = make_runner(
        make_agent(both, ask=True, tools=[_approval_tools()], output_type=ASKING), gate
    )
    handle = (await runner.send(ws, thread.id, "Go")).run
    assert handle is not None
    await handle.wait()
    first = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, first)).run is None
    second = AnswerDeferred(run_id=handle.run_id, tool_call_id="a1", approved=False)
    resumed = (await runner.answer(ws, second)).run
    assert resumed is not None
    await resumed.wait()
    assert await runner.resume(ws, handle.run_id) is None, "a finished run cannot resume"


async def test_a_run_can_be_stopped(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold")), tools=[app_tools]), gate)
    handle = (await runner.send(ws, thread.id, "Go")).run
    assert handle is not None
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    assert await runner.stop(handle.run_id)
    assert await runner.stop(handle.run_id) is False
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.status == "stopped"
    assert (await ws.run(handle.run_id)).status == "stopped"


async def test_a_claimed_thread_is_steered_not_started(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    runner = make_runner(make_agent(Script()), gate)
    async with ws.claim_thread(thread.id, holder="another process"):
        assert (await runner.send(ws, thread.id, "hello")).run is None
    assert [e.event.type for e in await ws.read()][-1] == "message_posted"


async def test_live_frames_reach_watchers(ws: Workspace, thread: Thread, gate: Gate) -> None:
    tools = FunctionToolset[Session[Gate]]()

    @dataclass(kw_only=True)
    class Progress(CustomEvent):
        done: int

    @tools.tool
    async def draft(ctx: RunContext[Session[Gate]]) -> str:
        await ctx.deps.app.wait()
        await ctx.emit(ArtifactDraft(kind="note", snapshot={"text": "Draft"}))
        await ctx.emit(Progress(done=1))
        return "drafted"

    script = Script(call("draft"), say("Here it is."))
    runner = make_runner(make_agent(script, tools=[tools]), gate)
    handle = (await runner.send(ws, thread.id, "Draft")).run
    assert handle is not None
    frames: list[LiveFrame] = []

    async def watch() -> None:
        frames.extend([frame async for frame in runner.watch(handle.run_id)])

    watcher = asyncio.create_task(watch())
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    gate.release.set()
    await handle.wait()
    await asyncio.wait_for(watcher, timeout=2)
    events = [frame.event for frame in frames]
    assert Draft(kind="note", data={"text": "Draft"}) in events
    assert AppLive(name="progress", data={"done": 1}) in events
    assert TextDelta(part=0, delta="Here it is.") in events
    assert {frame.run_id for frame in frames} == {handle.run_id}


def test_stream_events_translate_to_live_events() -> None:
    assert to_live(PartStartEvent(index=0, part=TextPart(""))) == [
        PartStarted(part=0, part_kind="text")
    ]
    assert to_live(PartStartEvent(index=1, part=ThinkingPart("hm"))) == [
        PartStarted(part=1, part_kind="thinking"),
        ThinkingDelta(part=1, delta="hm"),
    ]
    assert to_live(PartStartEvent(index=2, part=ThinkingPart(""))) == [
        PartStarted(part=2, part_kind="thinking")
    ]
    assert to_live(PartStartEvent(index=3, part=ToolCallPart(tool_name="t", args={"a": 1}))) == [
        PartStarted(part=3, part_kind="tool_call", tool_name="t"),
        ToolArgsDelta(part=3, delta='{"a":1}'),
    ]
    assert to_live(PartStartEvent(index=4, part=ToolCallPart(tool_name="t"))) == [
        PartStarted(part=4, part_kind="tool_call", tool_name="t")
    ]
    assert to_live(PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="x"))) == [
        TextDelta(part=0, delta="x")
    ]
    assert to_live(PartDeltaEvent(index=1, delta=ThinkingPartDelta(content_delta=None))) == []
    assert to_live(PartDeltaEvent(index=1, delta=ThinkingPartDelta(content_delta="y"))) == [
        ThinkingDelta(part=1, delta="y")
    ]
    assert to_live(PartDeltaEvent(index=3, delta=ToolCallPartDelta(args_delta={"b": 2}))) == [
        ToolArgsDelta(part=3, delta='{"b": 2}')
    ]
    assert to_live(PartDeltaEvent(index=3, delta=ToolCallPartDelta(args_delta=None))) == []
    assert to_live(PartEndEvent(index=0, part=TextPart("x"))) == [PartEnded(part=0)]
    assert to_live(FinalResultEvent(tool_name=None, tool_call_id=None)) == []


async def test_fanout_drops_the_oldest_frames_for_slow_watchers() -> None:
    channel = FanoutChannel(buffer=2)
    frames: list[LiveFrame] = []
    watcher = channel.watch("run_1")
    first = asyncio.ensure_future(watcher.__anext__())
    await asyncio.sleep(0)
    for n in range(4):
        await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta=str(n))))
    await channel.send(LiveFrame(run_id="run_2", event=TextDelta(part=0, delta="other run")))
    frames.append(await first)
    channel.close("run_1")
    frames.extend([frame async for frame in watcher])
    assert [f.event for f in frames] == [TextDelta(part=0, delta="2"), TextDelta(part=0, delta="3")]
    channel.close("run_1")


async def test_the_null_channel_drops_frames() -> None:
    await NullChannel().send(LiveFrame(run_id="r", event=TextDelta(part=0, delta="x")))


async def test_closing_a_full_watcher_still_ends_it() -> None:
    channel = FanoutChannel(buffer=1)
    watcher = channel.watch("run_1")
    pending = asyncio.ensure_future(watcher.__anext__())
    await asyncio.sleep(0)  # the watcher is now waiting for frames
    await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta="a")))
    await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta="b")))
    channel.close("run_1")  # the queue is full: the stale frame makes way for the end
    with pytest.raises(StopAsyncIteration):
        await pending


async def test_a_chat_reply_fills_only_unanswered_requests(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    two_questions = Script(
        lambda _: say("").__class__(
            parts=[
                *call("ask_user", call_id="q1", question="Day?").parts,
                *call("ask_user", call_id="q2", question="Time?").parts,
            ]
        ),
        say("Booked."),
    )
    runner = make_runner(make_agent(two_questions, ask=True, output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Book it")).run
    assert handle is not None
    await handle.wait()
    first = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, first)).run is None
    resumed = (await runner.send(ws, thread.id, "9am")).run
    assert resumed is not None
    await resumed.wait()
    answers = (await ws.run(handle.run_id)).status
    assert answers == "completed"
    assert two_questions.tool_returns(1) == ["Monday", "9am"]


async def test_a_late_watcher_gets_the_run_so_far() -> None:
    channel = FanoutChannel()
    for delta in ("Hel", "lo"):
        await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta=delta)))
    watcher = channel.watch("run_1")
    first, second = await watcher.__anext__(), await watcher.__anext__()
    assert [first.event, second.event] == [
        TextDelta(part=0, delta="Hel"),
        TextDelta(part=0, delta="lo"),
    ]
    channel.close("run_1")
    assert [frame async for frame in watcher] == []
    await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta="late")))
    assert [frame async for frame in channel.watch("run_1")] == [], "an ended run stays ended"


async def test_execute_routes_answers_and_stops(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Day?"), say("Monday."), call("hold"))
    runner = make_runner(make_agent(script, ask=True, tools=[app_tools], output_type=ASKING), gate)
    await started(await runner.send(ws, thread.id, "Plan")).wait()
    [paused] = await ws.runs(status="paused")
    answered = await runner.execute(
        ws, AnswerDeferred(run_id=paused.id, tool_call_id="q1", answer="Monday")
    )
    assert answered.type == "recorded"
    handle = runner.running(thread.id)
    assert handle is not None
    await handle.wait()
    running = started(await runner.send(ws, thread.id, "Wait for me"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    stopped = await runner.execute(ws, StopRun(run_id=running.run_id))
    assert stopped.type == "recorded"
    assert (await ws.run(running.run_id)).status == "stopped"


async def test_old_closed_runs_are_forgotten() -> None:
    channel = FanoutChannel(remember_closed=1)
    channel.close("run_1")
    channel.close("run_2")
    await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta="again")))
    watcher = channel.watch("run_1")
    assert (await watcher.__anext__()).event == TextDelta(part=0, delta="again")
    channel.close("run_1")
