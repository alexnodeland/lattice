"""The third review's probes of PR #35, kept as regression tests of ADR-0055.

N2b's patched commit passes on the ``cursor`` a reply now commits with, and N5 sends its last
message without asserting that it starts a run, since the run's hand-over may take it first.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import DeferredToolRequests, FunctionToolset

from artifactr.agent import Session
from artifactr.core import AnswerDeferred, PostMessage, Run, RunStatus, Thread, ThreadId, UserActor
from artifactr.workspace import Scope, Workspace
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
)

ASKING = [str, DeferredToolRequests]
BOB = UserActor(id="bob", name="Bob")


class After(HeldStorage):
    """Also holds a thread's paused runs once they are read, before the claimant acts on them."""

    def __init__(self) -> None:
        super().__init__()
        self.held_after_runs: Gate | None = None

    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        found = await super().runs(scope, thread_id=thread_id, status=status)
        if status == "paused" and (gate := self.held_after_runs) is not None:
            self.held_after_runs = None
            await gate.wait()
        return found


@pytest.fixture
def storage() -> After:
    return After()


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


def _seen(script: Script) -> list[str]:
    return [t for r in range(len(script.requests)) for t in script.prompt_texts(r)]


def _refuse_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    record = Workspace.save_cursor

    async def refuses(self: Workspace, name: str, seq: int) -> None:
        if name.endswith("/taken"):
            raise ConnectionError("the database blinked")
        await record(self, name, seq)

    monkeypatch.setattr(Workspace, "save_cursor", refuses)


# ─── N1. a message's reply races an answer committed without the claim ───────


async def test_n1_a_reply_racing_an_answer_strands_the_thread(
    storage: After, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    planning = storage.held_after_runs = Gate()
    bob = ws.as_actor(BOB)
    message = PostMessage(thread_id=thread.id, content="Tuesday, and book the room")
    sending = asyncio.create_task(runner.execute(bob, message, command_id="c1"))
    await _entered(planning)  # Bob's send holds the thread, having read the paused run
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday")
    sent = await runner.answer(ws, answer)  # Alice answers: the thread is claimed
    assert sent.run is None
    planning.release.set()
    result = await sending
    await settled(thread.id, runner)
    await asyncio.sleep(0.1)
    await settled(thread.id, runner)
    run = await ws.run(paused.run_id)
    posted = [
        e
        for e in await ws.read(threads={thread.id})
        if getattr(e.event, "content", None) == message.content
    ]
    assert result.ok, f"Bob's message was posted ({len(posted)}), but: {result.rejection}"
    assert run.status != "paused", f"stranded: run {run.status}, the model saw {_seen(script)}"


# ─── N2. a message used as the reply, then a resume that fails before it starts ──


async def test_n2_a_reply_whose_resume_fails_early_is_given_twice(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    failed: list[str] = []

    @contextlib.asynccontextmanager
    async def resuming_fails_once(session: Session[Any]) -> AsyncIterator[None]:
        if session.trigger == "resume" and not failed:
            failed.append(session.run_id)
            raise RuntimeError("the tracing backend blinked")
        yield

    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3)
    runner = runners(
        make_agent(script, ask=True, output_type=ASKING), turn_context=resuming_fails_once
    )
    paused = started(await runner.send(ws, thread.id, "Plan the launch"))
    await paused.wait()
    await runner.drain()
    resumed = started(await runner.send(ws, thread.id, "Monday"))  # the reply
    with pytest.raises(RuntimeError, match="blinked"):
        await resumed.wait()
    await runner.drain()
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    answers, conversation = script.answers(), script.conversation()
    assert answers == ["Monday"]
    assert conversation == ["Plan the launch", "Hello?"], (
        f"'Monday' was the answer {answers} and also a prompt: {conversation}"
    )


async def test_n2b_a_runner_closed_after_the_reply_is_committed(
    storage: After, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Plan the launch"))
    await paused.wait()
    await runner.drain()
    original = Workspace.commit
    closed: list[bool] = []
    closing: list[Any] = []

    async def commit_then_close(self: Workspace, command: Any, **options: Any) -> Any:
        result = await original(self, command, **options)
        if isinstance(command, AnswerDeferred) and not closed:
            closed.append(True)
            closing.append(asyncio.ensure_future(runner.aclose()))  # shutdown begins here
            await asyncio.sleep(0)
        return result

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(Workspace, "commit", commit_then_close)
        sent = await runner.send(ws, thread.id, "Monday")
    assert sent.run is None, "closed: no run starts"
    await asyncio.gather(*closing)
    restarted = runners(make_agent(script, ask=True, output_type=ASKING))
    started(await restarted.send(ws, thread.id, "Hello?"))
    await settled(thread.id, restarted)
    answers, conversation = script.answers(), script.conversation()
    assert answers == ["Monday"]
    assert "Monday" not in conversation, f"'Monday' was also a prompt: {conversation}"


# ─── N3. E1 in a paused thread: the old prompt becomes the reply ─────────────


async def test_n3_a_pause_whose_position_is_not_recorded_answers_with_its_prompt(
    ws: Workspace, thread: Thread, runners: MakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = Script(
        say("Hi."), call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3
    )
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    await started(await runner.send(ws, thread.id, "Hello")).wait()
    await runner.drain()
    with monkeypatch.context() as patched:
        _refuse_taken(patched)
        paused = started(await runner.send(ws, thread.id, "Plan the launch"))
        await paused.wait()
        await runner.drain()
    assert (await ws.run(paused.run_id)).status == "paused"
    await runner.send(ws, thread.id, "Tuesday")
    await settled(thread.id, runner)
    from artifactr.core import DeferredAnswered

    answered = [
        (e.event.tool_call_id, e.event.answer)
        for e in await ws.read(threads={thread.id})
        if isinstance(e.event, DeferredAnswered)
    ]
    run = await ws.run(paused.run_id)
    assert answered == [("q1", "Tuesday")], (
        f"answered {answered}; run {run.status}; the model's answers {script.answers()}, "
        f"its last conversation {script.conversation()}"
    )


# ─── N4. the C1 departure strands a bystander's message ──────────────────────


async def test_n4_a_message_deferred_to_a_holder_that_fails_before_it_starts(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    held = Gate()
    turns: list[str] = []

    @contextlib.asynccontextmanager
    async def second_fails(session: Session[Any]) -> AsyncIterator[None]:
        turns.append(session.run_id)
        if len(turns) == 2:
            await held.wait()
            raise RuntimeError("the tracing backend blinked")
        yield

    script = Script(say("Drafted."), *[say("ok")] * 3)
    runner = runners(make_agent(script), turn_context=second_fails)
    await started(await runner.send(ws, thread.id, "Plan the launch")).wait()
    await runner.drain()
    second = started(await runner.send(ws, thread.id, "Anything else?"))
    await _entered(held)
    bystander = await runner.send(ws.as_actor(BOB), thread.id, "Also book the big room")
    assert bystander.run is None, "Sent.run: 'its holder hands the thread over'"
    held.release.set()
    with pytest.raises(RuntimeError, match="blinked"):
        await second.wait()
    await settled(thread.id, runner)
    await asyncio.sleep(0.2)
    await settled(thread.id, runner)
    assert "Also book the big room" in _seen(script), (
        f"stranded in an idle thread: the model saw {_seen(script)}"
    )


async def test_n4b_a_stop_before_the_run_starts_strands_a_bystander(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    held = Gate()

    @contextlib.asynccontextmanager
    async def slow(session: Session[Any]) -> AsyncIterator[None]:
        if not held.release.is_set():
            await held.wait()
        yield

    script = Script(*[say("ok")] * 3)
    runner = runners(make_agent(script), turn_context=slow)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(held)
    bystander = await runner.send(ws.as_actor(BOB), thread.id, "Also book the big room")
    assert bystander.run is None
    assert await runner.stop(first.run_id)
    held.release.set()
    await settled(thread.id, runner)
    await asyncio.sleep(0.2)
    assert runner.running(thread.id) is None
    assert "Also book the big room" in _seen(script), f"stranded: the model saw {_seen(script)}"


# ─── N5. E1 in a thread with no taken position: a message in the window is lost ──


async def test_n5_a_first_run_whose_position_is_not_recorded_loses_what_it_missed(
    storage: After,
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    runners: MakeRunner,
    app_tools: FunctionToolset[Session[Gate]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Script(call("hold"), say("Done."), *[say("ok")] * 3)
    runner = runners(make_agent(script, tools=[app_tools]))
    slow = storage.held_subscribe = Gate()  # the watcher has not read the message yet
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    await _entered(gate)
    assert (await runner.send(ws, thread.id, "The venue changed")).run is None
    with monkeypatch.context() as patched:
        _refuse_taken(patched)
        gate.release.set()
        await handle.wait()
        await runner.drain()
    slow.release.set()
    await runner.send(ws, thread.id, "Hello?")
    await settled(thread.id, runner)
    assert "The venue changed" in _seen(script), (
        f"lost, not carried out again: the model saw {_seen(script)}"
    )


async def test_n5_control_with_the_position_recorded(
    storage: After,
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    runners: MakeRunner,
    app_tools: FunctionToolset[Session[Gate]],
) -> None:
    script = Script(call("hold"), say("Done."), *[say("ok")] * 3)
    runner = runners(make_agent(script, tools=[app_tools]))
    slow = storage.held_subscribe = Gate()
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    await _entered(gate)
    assert (await runner.send(ws, thread.id, "The venue changed")).run is None
    gate.release.set()
    await handle.wait()
    slow.release.set()
    await settled(thread.id, runner)
    assert "The venue changed" in _seen(script)
