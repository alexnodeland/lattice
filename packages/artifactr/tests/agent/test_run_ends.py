"""What is sent to a run as it ends is carried out once the run releases its thread.

A run stops taking messages when its agent's run is over, but holds its thread's claim until it
has recorded its end. A message or an answer sent in between finds the thread claimed, so it
starts or resumes nothing then: the run carries it out as it releases the thread.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic_ai import (
    AgentRunResult,
    DeferredToolRequests,
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
    HeldRelease,
    Script,
    call,
    make_agent,
    make_runner,
    say,
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
def storage() -> HeldRelease:
    return HeldRelease()


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


@pytest.mark.parametrize("elsewhere", [False, True], ids=["this process", "another process"])
async def test_a_message_sent_as_a_run_ends_starts_the_next_run(
    storage: HeldRelease, ws: Workspace, thread: Thread, gate: Gate, elsewhere: bool
) -> None:
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = make_runner(make_agent(script), gate)
    sender = make_runner(make_agent(Script()), gate) if elsewhere else runner
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert types(await ws.read())[-1] == "run_ended", "a client has seen the run end"
    assert (await sender.send(ws, thread.id, "Anything else?")).run is None, "its thread is held"
    releasing.release.set()
    await first.wait()
    following = runner.running(thread.id)
    assert following is not None, "the run that held the thread carries the message out"
    assert (await following.wait()).output == "Nothing else to do."
    assert script.prompt_texts(1) == ["Plan the launch", "Anything else?"]
    assert (await ws.run(following.run_id)).status == "completed"
    assert sender.running(thread.id) is None


async def test_a_message_the_agent_can_no_longer_take_starts_the_next_run(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ending = Gate()
    script = Script(say("Drafted."), say("Nothing else to do."))
    runner = make_runner(make_agent(script, capabilities=[HeldEnd(ending)]), gate)
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
    assert caplog.records == [], "which is not a failure of the watcher"
    following = runner.running(thread.id)
    assert following is not None
    await following.wait()
    assert script.prompt_texts(1) == ["Plan the launch", "Anything else?"]


@pytest.mark.parametrize("reply", ["answer", "message"])
async def test_a_reply_sent_as_a_run_pauses_resumes_it(
    storage: HeldRelease, ws: Workspace, thread: Thread, gate: Gate, reply: str
) -> None:
    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), say("Monday it is."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    if reply == "answer":
        answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
        sent = await runner.answer(ws, answer)
    else:
        sent = await runner.send(ws, thread.id, "Monday")
    assert sent.run is None, "the run holds its thread until it has paused"
    releasing.release.set()
    await first.wait()
    resumed = runner.running(thread.id)
    assert resumed is not None
    assert resumed.run_id == first.run_id
    assert (await resumed.wait()).output == "Monday it is."
    assert script.tool_returns(1) == ["Monday"]


async def test_an_answer_sent_as_a_run_pauses_waits_for_the_others(
    storage: HeldRelease, ws: Workspace, thread: Thread, gate: Gate
) -> None:
    releasing = storage.held = Gate()
    both = ModelResponse(
        parts=[
            ToolCallPart(tool_name="ask_user", args={"question": "Day?"}, tool_call_id="q1"),
            ToolCallPart(tool_name="ask_user", args={"question": "Time?"}, tool_call_id="q2"),
        ]
    )
    script = Script(both, say("Monday at noon."))
    runner = make_runner(make_agent(script, ask=True, output_type=ASKING), gate)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is None
    releasing.release.set()
    await first.wait()
    assert runner.running(thread.id) is None
    assert (await ws.run(first.run_id)).status == "paused", "q2 is unanswered"
    last = AnswerDeferred(run_id=first.run_id, tool_call_id="q2", answer="noon")
    assert (await started(await runner.answer(ws, last)).wait()).output == "Monday at noon."


async def _unreadable(*args: Any, **kwargs: Any) -> list[Envelope]:
    raise ConnectionError("the database went away")


async def test_carrying_out_what_a_run_missed_never_fails_the_run(
    storage: HeldRelease,
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releasing = storage.held = Gate()
    runner = make_runner(make_agent(Script(say("Drafted."))), gate)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await runner.send(ws, thread.id, "Anything else?")).run is None
    monkeypatch.setattr(Workspace, "read", _unreadable)
    with caplog.at_level(logging.ERROR, logger="artifactr.agent"):
        releasing.release.set()
        assert (await first.wait()).output == "Drafted."
    missed = f"carrying out what was sent as run {first.run_id} ended failed; it is left undone"
    assert [r.getMessage() for r in caplog.records] == [missed]
    assert runner.running(thread.id) is None
