"""Turns from the log: what is sent as a run ends, or while it holds its thread (ADR-0055).

A run stops taking messages when its agent's run is over, but holds its thread until it has
recorded its end. A message or an answer sent then asks for a turn that the run cannot give
yet. The run hands its thread over as it releases it, and whoever takes the thread starts the
turn with the oldest message no turn has taken, so each message is carried out once, in order.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic_ai import (
    AgentRunResult,
    DeferredToolRequests,
    FunctionToolset,
    ModelResponse,
    RunContext,
    ToolCallPart,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import WrapRunHandler

from artifactr.agent import Session
from artifactr.core import AnswerDeferred, Envelope, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import (
    Gate,
    HeldStorage,
    MakeRunner,
    Script,
    call,
    make_agent,
    say,
    settled,
    started,
    types,
)

ASKING = [str, DeferredToolRequests]


@dataclass
class HeldEnd(AbstractCapability[Session[Gate]]):
    """Holds each agent run at ``held`` once it is over, before the run records its end."""

    held: Gate

    async def wrap_run(self, ctx: Any, *, handler: WrapRunHandler) -> AgentRunResult[Any]:
        result = await handler()
        await self.held.wait()
        return result


@pytest.fixture
def storage() -> HeldStorage:
    return HeldStorage()


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


def _replies(first: str, count: int = 4) -> Script:
    """A model that replies ``first``, then "ok" as often as it is asked, up to ``count``."""
    return Script(say(first), *[say("ok")] * count)


# ─── a message sent as a run ends ─────────────────────────────────────────────


@pytest.mark.parametrize("elsewhere", [False, True], ids=["this process", "another process"])
async def test_a_message_sent_as_a_run_ends_starts_the_next_run(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner, elsewhere: bool
) -> None:
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = runners(make_agent(script))
    sender = runners(make_agent(Script())) if elsewhere else runner
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert types(await ws.read())[-1] == "run_ended", "a client has seen the run end"
    assert (await sender.send(ws, thread.id, "Anything else?")).run is None, "its thread is held"
    releasing.release.set()
    await first.wait()
    await runner.drain()
    following = runner.running(thread.id)
    assert following is not None, "the run hands its thread over to the next turn"
    assert (await following.wait()).output == "Nothing else to do."
    assert script.prompt_texts(1) == ["Plan the launch", "Anything else?"]
    assert sender.running(thread.id) is None


async def test_a_message_the_agent_can_no_longer_take_starts_the_next_run(
    ws: Workspace,
    thread: Thread,
    runners: MakeRunner,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ending = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = runners(make_agent(script, capabilities=[HeldEnd(ending)]))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(ending)
    enqueue, offered = RunContext.enqueue, asyncio.Event()

    def offer(ctx: RunContext[Any], *content: Any, **options: Any) -> str | None:
        offered.set()
        return enqueue(ctx, *content, **options)

    monkeypatch.setattr(RunContext, "enqueue", offer)
    with caplog.at_level(logging.ERROR, logger="artifactr.agent"):
        assert (await runner.send(ws, thread.id, "Anything else?")).run is None
        await asyncio.wait_for(offered.wait(), timeout=2)  # the run's watcher offers it, late
        ending.release.set()
        await first.wait()
        await runner.drain()
    assert caplog.records == [], "which is not a failure of the watcher"
    following = runner.running(thread.id)
    assert following is not None
    await following.wait()
    assert script.prompt_texts(1) == ["Plan the launch", "Anything else?"]


# ─── replies sent as a run pauses ─────────────────────────────────────────────


@pytest.mark.parametrize("reply", ["answer", "message"])
async def test_every_reply_sent_as_a_run_pauses_reaches_it(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner, reply: str
) -> None:
    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("Monday.")] * 3)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    if reply == "answer":
        answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
        sent = await runner.answer(ws, answer)
    else:
        sent = await runner.send(ws, thread.id, "Monday")
    assert sent.run is None, "the run holds its thread until it has paused"
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    releasing.release.set()
    await first.wait()
    await runner.drain()
    resumed = runner.running(thread.id)
    assert resumed is not None
    assert resumed.run_id == first.run_id
    await settled(runner, thread.id)
    assert script.answers() == ["Monday"]
    assert script.conversation()[-1] == "And book the big room", "the second reaches it too"


async def test_an_answer_sent_as_a_run_pauses_waits_for_the_others(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    both = ModelResponse(
        parts=[
            ToolCallPart(tool_name="ask_user", args={"question": "Day?"}, tool_call_id="q1"),
            ToolCallPart(tool_name="ask_user", args={"question": "Time?"}, tool_call_id="q2"),
        ]
    )
    script = Script(both, say("Monday at noon."))
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is None
    releasing.release.set()
    await first.wait()
    await runner.drain()
    assert runner.running(thread.id) is None
    assert (await ws.run(first.run_id)).status == "paused", "q2 is unanswered"
    last = AnswerDeferred(run_id=first.run_id, tool_call_id="q2", answer="noon")
    assert (await started(await runner.answer(ws, last)).wait()).output == "Monday at noon."


# ─── turns that fail ──────────────────────────────────────────────────────────


async def test_a_turn_that_fails_before_it_starts_is_not_carried_out_again(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    entered: list[str] = []

    @contextlib.asynccontextmanager
    async def flaky(session: Session[Any]) -> AsyncIterator[None]:
        entered.append(session.run_id)
        if len(entered) == 2:
            raise RuntimeError("the tracing backend blinked")
        yield

    script = Script(say("Drafted."))
    runner = runners(make_agent(script), turn_context=flaky)
    await started(await runner.send(ws, thread.id, "Plan the launch")).wait()
    second = started(await runner.send(ws, thread.id, "Anything else?"))
    with pytest.raises(RuntimeError, match="blinked"):
        await second.wait()
    await runner.drain()
    assert runner.running(thread.id) is None, "no turn for an old message, nor for this one"
    assert len(entered) == 2


async def test_a_turn_that_keeps_failing_is_one_turn_per_message(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    turns = 0

    @contextlib.asynccontextmanager
    async def broken(session: Session[Any]) -> AsyncIterator[None]:
        nonlocal turns
        turns += 1
        raise RuntimeError("the tracing backend is down")
        yield

    runner = runners(make_agent(Script()), turn_context=broken)
    for sent, content in enumerate(["Plan the launch", "Anything else?"], start=1):
        handle = started(await runner.send(ws, thread.id, content))
        with pytest.raises(RuntimeError, match="down"):
            await handle.wait()
        await runner.drain()
        assert (turns, runner.running(thread.id)) == (sent, None)


async def test_a_message_whose_turn_failed_is_not_carried_out_again(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    turns: list[str] = []

    @contextlib.asynccontextmanager
    async def second_fails(session: Session[Any]) -> AsyncIterator[None]:
        turns.append(session.run_id)
        if len(turns) == 2:
            raise RuntimeError("the tracing backend blinked")
        yield

    releasing = storage.held = Gate()
    runner = runners(make_agent(Script(say("Drafted."))), turn_context=second_fails)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    looking = storage.held_read = Gate()
    releasing.release.set()
    await first.wait()
    await _entered(looking)  # the run is handing its thread over, and waits to look
    second = started(await runner.send(ws, thread.id, "Anything else?"))  # the thread is free
    with pytest.raises(RuntimeError, match="blinked"):
        await second.wait()
    looking.release.set()
    await runner.drain()
    assert runner.running(thread.id) is None
    assert len(turns) == 2, "the hand-over finds the message taken"


async def test_a_resume_that_fails_before_it_starts_is_resumed_by_the_next_message(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    @contextlib.asynccontextmanager
    async def resuming_fails_once(session: Session[Any]) -> AsyncIterator[None]:
        if session.trigger == "resume" and not failed:
            failed.append(session.run_id)
            raise RuntimeError("the tracing backend blinked")
        yield

    failed: list[str] = []
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("Monday.")] * 3)
    agent = make_agent(script, ask=True, output_type=ASKING)
    runner = runners(agent, turn_context=resuming_fails_once)
    paused = started(await runner.send(ws, thread.id, "Plan the launch"))
    await paused.wait()
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday")
    with pytest.raises(RuntimeError, match="blinked"):
        await started(await runner.answer(ws, answer)).wait()
    await runner.drain()
    assert runner.running(thread.id) is None, "the failure is not retried by itself"
    assert (await ws.run(paused.run_id)).status == "paused"
    resumed = started(await runner.send(ws, thread.id, "Are you there?"))
    assert resumed.run_id == paused.run_id
    await settled(runner, thread.id)
    assert (await ws.run(paused.run_id)).status == "completed"
    assert script.conversation()[-1] == "Are you there?"


# ─── one turn per message, whoever takes the thread ───────────────────────────


async def test_a_message_is_carried_out_once_though_its_send_stalls(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    runner = runners(make_agent(_replies("Drafted.")))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    stalled = storage.held_claim = Gate()
    sending = asyncio.create_task(runner.send(ws, thread.id, "Anything else?"))
    await _entered(stalled)  # it committed the message and asked for a turn; then it stalls
    releasing.release.set()
    await first.wait()
    await settled(runner, thread.id)  # the hand-over carries the message out
    stalled.release.set()
    assert (await sending).run is None, "its message is taken"
    await runner.drain()
    assert len(await ws.runs(thread_id=thread.id)) == 2, "two runs for two messages"


async def test_a_turn_another_send_starts_takes_what_the_ending_run_missed_first(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    script = _replies("Drafted.")
    runner = runners(make_agent(script))
    other = runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await runner.send(ws, thread.id, "Anything missed?")).run is None
    looking = storage.held_read = Gate()
    releasing.release.set()
    await first.wait()
    await _entered(looking)  # the run is handing its thread over, and waits to look
    taking = started(await other.send(ws, thread.id, "And this"))  # another process takes it
    looking.release.set()
    await runner.drain()
    await settled(other, thread.id)
    assert runner.running(thread.id) is None, "the hand-over finds both taken"
    assert script.prompt_texts(1)[:2] == ["Plan the launch", "Anything missed?"], "first"
    assert script.conversation() == ["Plan the launch", "Anything missed?", "And this"]
    assert taking.run_id != first.run_id


async def test_a_run_that_ended_is_not_stopped_or_waited_for_as_it_hands_over(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await runner.send(ws, thread.id, "Anything else?")).run is None
    looking = storage.held_read = Gate()
    releasing.release.set()
    await first.wait()  # it does not wait for the hand-over
    await _entered(looking)
    assert runner.running(thread.id) is None
    assert not await runner.stop(first.run_id), "the run has ended, so there is none to stop"
    looking.release.set()
    await runner.drain()
    following = runner.running(thread.id)
    assert following is not None
    await following.wait()
    assert script.prompt_texts(1)[-1] == "Anything else?"


# ─── messages committed directly ─────────────────────────────────────────────


@pytest.mark.parametrize("when", ["as a run ends", "in an idle thread"])
async def test_a_message_posted_directly_starts_no_turn_but_the_next_turn_takes_it(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner, when: str
) -> None:
    releasing = storage.held = Gate()
    script = _replies("Drafted.")
    runner = runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    if when == "as a run ends":
        await ws.post_message(thread.id, "FYI: the venue changed")
    releasing.release.set()
    await first.wait()
    if when == "in an idle thread":
        await ws.post_message(thread.id, "FYI: the venue changed")
    await runner.drain()
    assert runner.running(thread.id) is None, "it starts no turn"
    started(await runner.send(ws, thread.id, "Anything else?"))
    await settled(runner, thread.id)
    assert script.conversation() == ["Plan the launch", "FYI: the venue changed", "Anything else?"]


# ─── what the Runner does besides ─────────────────────────────────────────────


async def test_what_a_run_without_the_runner_was_told_counts_as_taken(
    ws: Workspace, thread: Thread, gate: Gate, runners: MakeRunner
) -> None:
    await ws.post_message(thread.id, "An old message")
    before = Script(say("An old reply."))
    await make_agent(before).run("An old message", deps=Session.start(ws, thread.id, app=gate))
    script = Script(say("Hello again."))
    await started(await runners(make_agent(script)).send(ws, thread.id, "Hi")).wait()
    assert script.prompt_texts(0) == ["An old message", "Hi"], "not the old message again"


async def test_resuming_a_run_that_is_not_paused_does_nothing(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script(say("Done."))))
    first = started(await runner.send(ws, thread.id, "Go"))
    await first.wait()
    await runner.drain()
    assert await runner.resume(ws, first.run_id) is None


async def _unreadable(*args: Any, **kwargs: Any) -> list[Envelope]:
    raise ConnectionError("the database went away")


async def test_a_hand_over_that_fails_is_logged_and_the_next_turn_carries_it_out(
    storage: HeldStorage,
    ws: Workspace,
    thread: Thread,
    runners: MakeRunner,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releasing = storage.held = Gate()
    script = _replies("Drafted.")
    runner = runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await runner.send(ws, thread.id, "Anything else?")).run is None
    with monkeypatch.context() as patched, caplog.at_level(logging.ERROR, logger="artifactr"):
        patched.setattr(Workspace, "read", _unreadable)
        releasing.release.set()
        assert (await first.wait()).output == "Drafted.", "the run keeps its result"
        await runner.drain()
    failed = f"handing thread {thread.id} over failed; its next turn carries out what was sent"
    assert [r.getMessage() for r in caplog.records] == [failed]
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(runner, thread.id)
    assert script.conversation() == ["Plan the launch", "Anything else?", "Hello?"]


async def test_a_run_whose_position_cannot_be_recorded_keeps_its_result(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    runners: MakeRunner,
    app_tools: FunctionToolset[Session[Gate]],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runners(make_agent(Script(call("hold"), say("Done.")), tools=[app_tools]))
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    await _entered(gate)

    async def unsaved(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("the database went away")

    with monkeypatch.context() as patched, caplog.at_level(logging.ERROR, logger="artifactr"):
        patched.setattr(Workspace, "save_cursor", unsaved)
        gate.release.set()
        assert (await handle.wait()).output == "Done."
    assert [r.getMessage() for r in caplog.records] == [
        f"recording what run {handle.run_id} took failed"
    ]
