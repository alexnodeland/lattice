"""Who takes a thread, and when (ADR-0055).

Covered here: a workspace whose other threads are busy; a claimant cancelled, or its runner
closed, at each step; a resume by answers; and a message committed directly in a paused
thread.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import (
    DeferredToolRequests,
    FunctionToolset,
    ModelResponse,
    RunContext,
    ToolCallPart,
)

from artifactr.agent import Session
from artifactr.core import AnswerDeferred, DeferredAnswered, Thread, UserActor
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
)

ASKING = [str, DeferredToolRequests]
BOB = UserActor(id="bob", name="Bob")


@pytest.fixture
def storage() -> HeldStorage:
    return HeldStorage()


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    """The test's thread, in a workspace where another thread was busy first."""
    elsewhere = await ws.create_thread("Elsewhere")
    await ws.post_message(elsewhere.id, "Over here")
    return await ws.create_thread("Launch")


async def _entered(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


def _both_questions() -> ModelResponse:
    return ModelResponse(
        parts=[
            ToolCallPart(tool_name="ask_user", args={"question": "Day?"}, tool_call_id="q1"),
            ToolCallPart(tool_name="ask_user", args={"question": "Time?"}, tool_call_id="q2"),
        ]
    )


# ─── the log's head in another thread ─────────────────────────────────────────


async def test_resuming_while_the_head_is_another_threads_ends(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script(say("Done."))))
    first = started(await runner.send(ws, thread.id, "Go"))
    await first.wait()
    await runner.drain()
    elsewhere = await ws.create_thread("Elsewhere again")
    await ws.post_message(elsewhere.id, "Hello over there")
    claims = storage.claims
    assert await runner.resume(ws, first.run_id) is None, "the run is not paused"
    assert storage.claims - claims <= 2


async def test_a_partial_answer_while_another_thread_commits_ends(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script(_both_questions(), say("ok")), ask=True, output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    elsewhere = await ws.create_thread("Elsewhere again")
    asking = storage.held_head = Gate()
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday")
    answering = asyncio.create_task(runner.answer(ws, answer))
    await _entered(asking)  # the answer is about to ask for a turn up to the log's head
    await ws.post_message(elsewhere.id, "Meanwhile, in another thread")
    claims = storage.claims
    asking.release.set()
    assert (await answering).run is None, "q2 is unanswered"
    assert storage.claims - claims <= 2
    assert (await ws.run(paused.run_id)).status == "paused"


# ─── a claimant cancelled, or a runner closed, before its turn starts ────────


@pytest.mark.parametrize(
    "when",
    [
        "as it asks",
        "as it reads what the agent was last told",
        "as it plans",
        "as its turn begins",
    ],
)
async def test_a_send_cancelled_at_any_step_has_its_message_carried_out_once(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner, when: str
) -> None:
    script = Script(*[say("ok")] * 3)
    beginning = Gate()

    @contextlib.asynccontextmanager
    async def begins(session: Session[Any]) -> AsyncIterator[None]:
        if when == "as its turn begins" and not beginning.release.is_set():
            await beginning.wait()
        yield

    runner = runners(make_agent(script), turn_context=begins)
    if when == "as it asks":
        held = storage.held_read = Gate()
    elif when == "as it reads what the agent was last told":
        held = storage.held_history = Gate()  # a thread with no position reads its history
    elif when == "as it plans":
        held = storage.held_runs = Gate()
    else:
        held = beginning
    sending = asyncio.create_task(runner.send(ws, thread.id, "Plan the launch"))
    await _entered(held)
    sending.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sending
    held.release.set()
    await settled(thread.id, runner)
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    assert script.conversation() == ["Plan the launch", "Hello?"]


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("as it plans", ["Plan the launch", "Anything else?", "Hello?"]),
        ("before its turn starts", ["Plan the launch", "Anything else?", "Hello?"]),
        ("once its turn has started", ["Plan the launch", "Hello?"]),
    ],
)
async def test_a_runner_closed_as_it_hands_over_consumes_a_message_at_most_once(
    storage: HeldStorage,
    ws: Workspace,
    thread: Thread,
    runners: MakeRunner,
    when: str,
    expected: list[str],
) -> None:
    releasing = storage.held = Gate()
    script = Script(say("Drafted."), *[say("ok")] * 3)
    runner = runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    assert (await runner.send(ws, thread.id, "Anything else?")).run is None
    if when == "as it plans":
        closing = storage.held_runs = Gate()
    elif when == "before its turn starts":
        closing = storage.held_history = Gate()  # the turn loads the thread's history first
    else:
        closing = storage.held_thread = Gate()  # the run has recorded its start
    releasing.release.set()
    await first.wait()
    await _entered(closing)
    await runner.aclose()
    restarted = runners(make_agent(script))
    started(await restarted.send(ws, thread.id, "Hello?"))
    await settled(thread.id, restarted)
    assert script.conversation() == expected, "a run stopped once it started keeps its input"


async def test_a_runner_closed_as_a_send_plans_starts_no_run(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(say("ok"))
    runner = runners(make_agent(script))
    planning = storage.held_runs = Gate()
    sending = asyncio.create_task(runner.send(ws, thread.id, "Go"))
    await _entered(planning)
    await runner.aclose()
    planning.release.set()
    assert (await sending).run is None, "no run starts once the runner is closed"
    restarted = runners(make_agent(script))
    started(await restarted.send(ws, thread.id, "Still there?"))
    await settled(thread.id, restarted)
    assert script.conversation() == ["Go", "Still there?"]


# ─── a resume by answers ──────────────────────────────────────────────────────


async def test_a_resume_that_fails_before_it_starts_leaves_its_messages_for_the_next(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    failed: list[str] = []

    @contextlib.asynccontextmanager
    async def resuming_fails_once(session: Session[Any]) -> AsyncIterator[None]:
        if session.trigger == "resume" and not failed:
            failed.append(session.run_id)
            raise RuntimeError("the tracing backend blinked")
        yield

    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3)
    agent = make_agent(script, ask=True, output_type=ASKING)
    runner = runners(agent, turn_context=resuming_fails_once)
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is None
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    releasing.release.set()
    await first.wait()
    await settled(thread.id, runner)
    assert failed, "the resume failed before it started"
    started(await runner.send(ws, thread.id, "Hello?"))
    await settled(thread.id, runner)
    assert script.conversation() == ["Plan the launch", "And book the big room", "Hello?"]
    assert script.answers() == ["Monday"]


async def test_a_resume_gives_the_run_its_messages_however_slow_its_watcher(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    releasing = storage.held = Gate()
    script = Script(call("ask_user", call_id="q1", question="Which day?"), *[say("ok")] * 3)
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)
    answer = AnswerDeferred(run_id=first.run_id, tool_call_id="q1", answer="Monday")
    assert (await runner.answer(ws, answer)).run is None
    assert (await runner.send(ws, thread.id, "And book the big room")).run is None
    slow = storage.held_subscribe = Gate()  # the resumed run's watcher reads late
    releasing.release.set()
    await first.wait()
    await runner.drain()
    resumed = runner.running(thread.id)
    assert resumed is not None
    await resumed.wait()  # the model answered at once
    slow.release.set()
    await settled(thread.id, runner)
    assert script.prompt_texts(1)[-1] == "And book the big room", "with the answer, at once"
    assert len(script.requests) == 2


# ─── a message is a message ───────────────────────────────────────────────────


def _approval_tools() -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool(requires_approval=True)
    async def publish(ctx: RunContext[Session[Gate]], channel: str) -> str:
        """Publish the plan."""
        return f"published to {channel}"

    return tools


async def test_a_message_posted_directly_in_a_paused_thread_is_its_reply(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    both = ModelResponse(
        parts=[
            *call("ask_user", call_id="q1", question="Day?").parts,
            *call("publish", call_id="a1", channel="blog").parts,
        ]
    )
    script = Script(both, say("ok"))
    agent = make_agent(script, ask=True, tools=[_approval_tools()], output_type=ASKING)
    runner = runners(agent)
    paused = started(await runner.send(ws, thread.id, "Go"))
    await paused.wait()
    await runner.drain()
    await ws.as_actor(BOB).post_message(thread.id, "Not yet, legal hasn't signed off")
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer="Monday")
    resumed = (await runner.answer(ws, answer)).run
    assert resumed is not None, "Bob's message declines the approval, so the run resumes"
    await settled(thread.id, runner)
    [declined] = [
        (e.actor, e.event.approved, e.event.answer)
        for e in await ws.read(threads={thread.id})
        if isinstance(e.event, DeferredAnswered) and e.event.tool_call_id == "a1"
    ]
    assert declined == (BOB, False, "Not yet, legal hasn't signed off")


async def test_resume_takes_a_message_posted_directly_as_the_reply(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), say("Monday then."))
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    await ws.as_actor(BOB).post_message(thread.id, "Monday")
    resumed = await runner.resume(ws, paused.run_id)
    assert resumed is not None
    assert (await resumed.wait()).output == "Monday then."
    assert script.answers() == ["Monday"]


async def test_a_notice_posted_in_a_paused_thread_answers_nothing(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"), say("Monday then."))
    runner = runners(make_agent(script, ask=True, output_type=ASKING))
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    await runner.drain()
    await ws.as_actor(BOB).post_message(thread.id, "CI is green", kind="notice")
    assert await runner.resume(ws, paused.run_id) is None
    assert (await ws.run(paused.run_id)).status == "paused"


# ─── the rules that keep a message from being stranded ───────────────────────


async def test_a_claimant_that_plans_nothing_looks_again_for_what_it_refused(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    script = Script(say("Done."), *[say("ok")] * 3)
    runner, other = runners(make_agent(script)), runners(make_agent(script))
    first = started(await runner.send(ws, thread.id, "Go"))
    await first.wait()
    await runner.drain()
    reading = storage.held_log = Gate()
    resuming = asyncio.create_task(runner.resume(ws, first.run_id))  # it plans nothing
    await _entered(reading)  # it has read the log, holding the thread
    assert (await other.send(ws.as_actor(BOB), thread.id, "Also book the big room")).run is None
    reading.release.set()
    following = await resuming  # having planned nothing, it looks again and takes Bob's
    assert following is not None
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Go", "Also book the big room"]


async def test_a_run_that_took_nothing_reads_what_was_asked_after_its_release(
    storage: HeldStorage, ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    failing = [True]

    @contextlib.asynccontextmanager
    async def fails_once(session: Session[Any]) -> AsyncIterator[None]:
        if failing.pop() if failing else False:
            raise RuntimeError("the tracing backend blinked")
        yield

    script = Script(*[say("ok")] * 3)
    runner = runners(make_agent(script), turn_context=fails_once)
    other = runners(make_agent(script))
    releasing = storage.held = Gate()
    first = started(await runner.send(ws, thread.id, "Plan the launch"))
    await _entered(releasing)  # it failed, took nothing, and is releasing the thread
    assert (await other.send(ws.as_actor(BOB), thread.id, "Also book the big room")).run is None
    releasing.release.set()
    await asyncio.gather(first.task, return_exceptions=True)
    await settled(thread.id, runner, other)
    assert script.conversation() == ["Plan the launch", "Also book the big room"]


async def test_a_run_stopped_at_once_releases_its_thread(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    runner = runners(make_agent(Script(say("ok"))))
    handle = started(await runner.send(ws, thread.id, "Go"))
    handle.task.cancel()  # before the loop runs anything else: its task started eagerly
    await asyncio.gather(handle.task, return_exceptions=True)
    async with asyncio.timeout(2), ws.claim_thread(thread.id, holder="next"):
        pass
