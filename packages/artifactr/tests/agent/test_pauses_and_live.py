"""Pausing for people, stopping runs, and live output."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

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
    ToolReturnPart,
)
from pydantic_ai.messages import CustomEvent, FinalResultEvent

from artifactr.agent import (
    ArtifactDraft,
    FanoutChannel,
    NullChannel,
    Session,
    forward_live,
    to_live,
)
from artifactr.core import (
    AnswerDeferred,
    AppLive,
    Draft,
    LiveFrame,
    PartEnded,
    PartStarted,
    Recorded,
    RunEnded,
    RunPaused,
    RunStarted,
    StopRun,
    TextDelta,
    ThinkingDelta,
    Thread,
    ToolArgsDelta,
    rules,
)
from artifactr.workspace import Workspace
from tests.agent.conftest import (
    Gate,
    Script,
    ask,
    call,
    event_as,
    in_words,
    make_agent,
    make_runner,
    say,
    started,
)

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
    script = Script(ask("q1", "Which day?"), say("Monday it is."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Plan the launch")).run
    assert handle is not None
    paused = await handle.wait()
    assert isinstance(paused.output, DeferredToolRequests)
    run = await ws.run(handle.run_id)
    assert (run.status, [r.tool_call_id for r in run.pending]) == ("paused", ["q1"])
    [pause] = [e.event for e in await ws.read() if isinstance(e.event, RunPaused)]
    assert pause.usage is not None
    assert pause.usage.requests == 1, "what the run used before it paused"
    resumed = (
        await runner.answer(
            ws, AnswerDeferred(run_id=run.id, tool_call_id="q1", answer=in_words("Monday"))
        )
    ).run
    assert resumed is not None
    assert resumed.run_id == handle.run_id
    assert (await resumed.wait()).output == "Monday it is."
    assert (await ws.run(run.id)).status == "completed"
    assert script.tool_returns(1) == ["Monday"]


async def test_the_agent_is_told_each_question_beside_what_was_chosen(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(ask("q1", "Which day?"), say("Tuesday it is."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    await started(await runner.send(ws, thread.id, "Plan the launch")).wait()
    [run] = await ws.runs(status="paused")
    tools = {tool.name: tool for tool in script.infos[0].function_tools}
    assert tools["ask_user"].parameters_json_schema["properties"]["questions"]["maxItems"] == 4
    chosen = AnswerDeferred(
        run_id=run.id, tool_call_id="q1", answer={"answers": [{"selected": ["Tuesday"]}]}
    )
    await started(await runner.answer(ws, chosen)).wait()
    [returned] = [
        part.content for part in script.requests[1][-1].parts if isinstance(part, ToolReturnPart)
    ]
    assert returned == [{"question": "Which day?", "selected": ["Tuesday"]}]


async def test_a_question_answered_as_a_string_before_resumes_after(
    ws: Workspace, thread: Thread, gate: Gate, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = Script(ask("q1", "Which day?"), say("Monday then."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    with monkeypatch.context() as before:  # as core committed answers before it held them
        before.setattr(rules, "check_answer", lambda args, answer: None)
        await ws.commit(AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday"))
    resumed = await runner.resume(ws, paused.run_id)
    assert resumed is not None
    assert (await resumed.wait()).output == "Monday then."
    assert script.tool_returns(1) == ["Monday"], "passed through as it was committed"


async def test_a_chat_message_answers_a_paused_run(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(ask("q1", "Which day?"), say("Monday then."))
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
        lambda _: ask("q1", "Day?").__class__(
            parts=[
                *ask("q1", "Day?").parts,
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
    first = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer=in_words("Monday"))
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
    assert ended.usage is not None
    assert ended.usage.requests == 1, "what it used so far"
    assert (await ws.run(handle.run_id)).status == "stopped"


async def test_closing_a_runner_stops_its_runs(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold")), tools=[app_tools]), gate)
    handle = (await runner.send(ws, thread.id, "Go")).run
    assert handle is not None
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    await runner.aclose()
    assert runner.running(thread.id) is None
    assert (await ws.run(handle.run_id)).status == "stopped"
    assert (await runner.send(ws, thread.id, "Again")).run is None, "and starts no more"


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
    assert TextDelta(part=0, delta="Here it is.", offset=0) in events
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
                *ask("q1", "Day?").parts,
                *ask("q2", "Time?").parts,
            ]
        ),
        say("Booked."),
    )
    runner = make_runner(make_agent(two_questions, ask=True, output_type=ASKING), gate)
    handle = (await runner.send(ws, thread.id, "Book it")).run
    assert handle is not None
    await handle.wait()
    first = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer=in_words("Monday"))
    unanswered = await runner.answer(ws, first)
    assert (unanswered.run, unanswered.outcome.run_id) == (None, None), "q2 is still open"
    replied = await runner.send(ws, thread.id, "9am")
    resumed = replied.run
    assert resumed is not None
    assert replied.outcome.run_id == handle.run_id, "the reply resumed the paused run"
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
    channel.open("run_1")  # until it resumes
    await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta="again")))
    assert (await channel.watch("run_1").__anext__()).event == TextDelta(part=0, delta="again")


class _Deps:
    run_id = "run_1"


def _ctx() -> Any:
    """What ``forward_live`` reads of a run context: the session's run id."""
    return SimpleNamespace(deps=_Deps())


async def _events(*events: Any) -> AsyncIterator[Any]:
    for event in events:
        yield event


async def _forwarded(coalesce: float, *events: Any) -> list[Any]:
    """The live events ``forward_live`` sends for a stream of events, in order."""
    frames: list[LiveFrame] = []

    class Channel:
        async def send(self, frame: LiveFrame) -> None:
            frames.append(frame)

    await forward_live(Channel(), coalesce=coalesce)(_ctx(), _events(*events))
    assert {frame.run_id for frame in frames} <= {"run_1"}
    return [frame.event for frame in frames]


def _text(index: int, delta: str) -> PartDeltaEvent:
    return PartDeltaEvent(index=index, delta=TextPartDelta(content_delta=delta))


def _thought(index: int, delta: str) -> PartDeltaEvent:
    return PartDeltaEvent(index=index, delta=ThinkingPartDelta(content_delta=delta))


async def test_deltas_are_gathered_for_a_moment_and_sent_with_their_offsets() -> None:
    sent = await _forwarded(
        0.5,
        PartStartEvent(index=0, part=ThinkingPart("hm")),
        _thought(0, ", so"),
        PartEndEvent(index=0, part=ThinkingPart("hm, so")),
        PartStartEvent(index=1, part=TextPart("")),
        _text(1, "Hel"),
        _text(1, "lo"),
        _text(1, " there"),
        PartEndEvent(index=1, part=TextPart("Hello there")),
        PartStartEvent(index=2, part=TextPart("Again")),
        _text(2, "!"),
    )
    assert sent == [
        PartStarted(part=0, part_kind="thinking"),
        ThinkingDelta(part=0, delta="hm, so", offset=0),
        PartEnded(part=0),
        PartStarted(part=1, part_kind="text"),
        TextDelta(part=1, delta="Hello there", offset=0),
        PartEnded(part=1),
        PartStarted(part=2, part_kind="text"),
        TextDelta(part=2, delta="Again!", offset=0),
    ], "one frame a part, each other event sending what was gathered first, and the end the rest"


async def test_deltas_gathered_past_the_moment_are_sent_as_they_stand() -> None:
    frames: list[LiveFrame] = []
    sent = asyncio.Event()

    class Channel:
        async def send(self, frame: LiveFrame) -> None:
            frames.append(frame)
            sent.set()

    async def slowly() -> AsyncIterator[Any]:
        yield _text(0, "Hel")
        yield _text(0, "lo")
        await sent.wait()  # the moment passed, and what was gathered went
        sent.clear()
        yield _text(0, " there")
        await sent.wait()

    await forward_live(Channel(), coalesce=0.02)(_ctx(), slowly())
    assert [f.event for f in frames] == [
        TextDelta(part=0, delta="Hello", offset=0),
        TextDelta(part=0, delta=" there", offset=5),
    ], "each delta's offset is where it starts in its part"


async def test_without_a_moment_each_delta_is_sent_as_it_comes() -> None:
    sent = await _forwarded(0, _text(0, "a"), _text(0, "b"), _thought(1, "c"), _text(0, "d"))
    assert sent == [
        TextDelta(part=0, delta="a", offset=0),
        TextDelta(part=0, delta="b", offset=1),
        ThinkingDelta(part=1, delta="c", offset=0),
        TextDelta(part=0, delta="d", offset=2),
    ]


async def test_offsets_count_from_zero_at_each_parts_start() -> None:
    """A model response's parts are numbered from 0 again: so are their offsets."""
    sent = await _forwarded(
        0,
        PartStartEvent(index=0, part=TextPart("")),
        _text(0, "first"),
        PartEndEvent(index=0, part=TextPart("first")),
        PartStartEvent(index=0, part=TextPart("")),  # the next response's part 0
        _text(0, "second"),
    )
    assert [e for e in sent if isinstance(e, TextDelta)] == [
        TextDelta(part=0, delta="first", offset=0),
        TextDelta(part=0, delta="second", offset=0),
    ]


async def test_a_handler_cancelled_with_a_flush_pending_sends_what_it_gathered() -> None:
    frames: list[LiveFrame] = []

    class Channel:
        async def send(self, frame: LiveFrame) -> None:
            frames.append(frame)

    async def stalling() -> AsyncIterator[Any]:
        yield _text(0, "Hel")
        yield _text(0, "lo")
        await asyncio.Event().wait()

    async def handle() -> None:
        await forward_live(Channel(), coalesce=5.0)(_ctx(), stalling())

    handling = asyncio.create_task(handle())
    await asyncio.sleep(0.01)
    assert frames == [], "gathered, not sent yet"
    handling.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handling
    assert [f.event for f in frames] == [TextDelta(part=0, delta="Hello", offset=0)]
    await asyncio.sleep(0.01)
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()], "no flush left"


async def test_a_delta_sent_twice_places_itself_by_its_offset() -> None:
    """What a client does with offsets: a replayed delta lands where it belongs, once."""
    parts: dict[int, str] = {}
    for delta in [
        TextDelta(part=0, delta="Hello", offset=0),
        TextDelta(part=0, delta=" there", offset=5),
        TextDelta(part=0, delta=" there", offset=5),  # replayed on reconnect
        TextDelta(part=0, delta="Hello there", offset=0),  # gathered differently, replayed
        TextDelta(part=0, delta="!", offset=11),
        TextDelta(part=0, delta=" Bye", offset=20),  # past the end: a frame it was never sent
        TextDelta(part=0, delta="."),  # from an earlier server: no offset
    ]:
        text = parts.get(delta.part, "")
        at = len(text) if delta.offset is None or delta.offset > len(text) else delta.offset
        parts[delta.part] = text[:at] + delta.delta
    assert parts == {0: "Hello there! Bye."}


async def test_execute_routes_answers_and_stops(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    script = Script(ask("q1", "Day?"), say("Monday."), call("hold"))
    runner = make_runner(make_agent(script, ask=True, tools=[app_tools], output_type=ASKING), gate)
    await started(await runner.send(ws, thread.id, "Plan")).wait()
    [paused] = await ws.runs(status="paused")
    answer = AnswerDeferred(run_id=paused.id, tool_call_id="q1", answer=in_words("Monday"))
    answered = await runner.execute(ws, answer, command_id="c1")
    assert isinstance(answered.outcome, Recorded)
    assert answered.outcome.run_id == paused.id, "it resumed the run"
    handle = runner.running(thread.id)
    assert handle is not None
    await handle.wait()
    running = started(await runner.send(ws, thread.id, "Wait for me"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    stopped = await runner.execute(ws, StopRun(run_id=running.run_id), command_id="c2")
    assert stopped.outcome == Recorded()
    assert (await ws.run(running.run_id)).status == "stopped"


async def test_old_closed_runs_are_forgotten() -> None:
    channel = FanoutChannel(remember_closed=1)
    channel.close("run_1")
    channel.close("run_2")
    await channel.send(LiveFrame(run_id="run_1", event=TextDelta(part=0, delta="again")))
    watcher = channel.watch("run_1")
    assert (await watcher.__anext__()).event == TextDelta(part=0, delta="again")
    channel.close("run_1")


async def _starts(ws: Workspace) -> list[tuple[str, tuple[str, ...]]]:
    return [
        (e.event.trigger, e.event.message_ids)
        for e in await ws.read()
        if isinstance(e.event, RunStarted)
    ]


async def test_run_started_names_the_messages_its_start_carries_out(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(ask("q1", "Which day?"), say("Monday then."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    await started(await runner.send(ws, thread.id, "Plan it", message_id="m1")).wait()
    await started(await runner.send(ws, thread.id, "Monday", message_id="m2")).wait()
    assert await _starts(ws) == [("message", ("m1",)), ("resume", ("m2",))], "the reply too"


async def test_a_resumed_run_names_the_messages_it_takes_as_its_prompt(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(ask("q1", "Which day?"), say("Monday then."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    handle = started(await runner.send(ws, thread.id, "Plan it", message_id="m1"))
    await handle.wait()
    await ws.commit(
        AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer=in_words("Monday"))
    )
    await ws.post_message(thread.id, "And at noon", message_id="m2")
    resumed = await runner.resume(ws, handle.run_id)
    assert resumed is not None
    await resumed.wait()
    assert await _starts(ws) == [("message", ("m1",)), ("resume", ("m2",))]
