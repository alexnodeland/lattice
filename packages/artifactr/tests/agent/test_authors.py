"""One author per turn: a turn acts for whoever started it, and takes only their messages."""

import asyncio
import logging

import pytest
from pydantic_ai import DeferredToolRequests, FunctionToolset

from artifactr.agent import Session
from artifactr.agent.runner import NOT_TAKEN
from artifactr.core import (
    Actor,
    AgentActor,
    AnswerDeferred,
    Forbidden,
    MessagePosted,
    RunEnded,
    RunStarted,
    SystemActor,
    Thread,
    UserActor,
    acting_for,
)
from artifactr.workspace import Access, Authorize, InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import (
    ALICE,
    Gate,
    Script,
    ask,
    call,
    event_as,
    in_words,
    make_agent,
    make_runner,
    say,
    settle,
    settled,
    started,
)

BOB = UserActor(id="bob", name="Bob")


async def _for_whom(ws: Workspace) -> list[str | None]:
    """Whom each run segment acted for, in order, from the actor of its ``run_started``."""
    acted: list[str | None] = []
    for envelope in await ws.read():
        if isinstance(envelope.event, RunStarted):
            assert isinstance(envelope.actor, AgentActor)
            behalf = envelope.actor.on_behalf_of
            acted.append(None if behalf is None else behalf.participant)
    return acted


async def test_a_message_from_someone_else_during_a_run_starts_the_next_turn(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    script = Script(call("hold"), say("Friday it is."), say("Monday, then."), say("Invited."))
    runner = make_runner(make_agent(script, tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Plan the launch for Friday"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    assert (await runner.send(ws.as_actor(BOB), thread.id, "Make it Monday")).run is None
    assert (await runner.send(ws, thread.id, "And invite the team")).run is None
    await settle()
    gate.release.set()
    await handle.wait()
    assert "Make it Monday" not in script.prompt_texts(1), "Bob's message is not Alice's turn's"
    await settled(thread.id, runner)
    assert await _for_whom(ws) == ["user:alice", "user:bob", "user:alice"]
    assert script.prompt_texts(2)[-1] == "Make it Monday"
    assert script.prompt_texts(3)[-1] == "And invite the team"


async def test_messages_waiting_for_a_turn_are_split_by_author(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("Noted."), say("Reminded."), say("Noted too."))
    runner = make_runner(make_agent(script), gate)
    await ws.post_message(thread.id, "Ship Friday")  # committed without asking for a turn
    await ws.as_actor(SystemActor()).post_message(thread.id, "A reminder")
    await started(await runner.send(ws.as_actor(BOB), thread.id, "Ship Monday")).wait()
    await settled(thread.id, runner)
    assert await _for_whom(ws) == ["user:alice", None, "user:bob"], "the system's acts for no one"
    assert [script.prompt_texts(i)[-1] for i in range(3)] == [
        "Ship Friday",
        "A reminder",
        "Ship Monday",
    ]


async def test_a_resumed_run_acts_for_whoever_answered_it(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    asking = [str, DeferredToolRequests]
    script = Script(ask("q1", "Which day?"), say("Monday."), say("Hi Bob."))
    runner = make_runner(make_agent(script, ask=True, output_type=asking), gate)
    bob = ws.as_actor(BOB)
    handle = started(await runner.send(bob, thread.id, "Plan it"))
    await handle.wait()
    await ws.commit(
        AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer=in_words("Monday"))
    )
    resumed = started(await runner.send(bob, thread.id, "Any news?"))
    await resumed.wait()
    assert resumed.run_id == handle.run_id, "Bob's message resumes the answered run"
    assert "Any news?" not in script.prompt_texts(1), "but the run acts for Alice, who answered"
    await settled(thread.id, runner)
    assert await _for_whom(ws) == ["user:bob", "user:alice", "user:bob"]
    assert script.prompt_texts(2)[-1] == "Any news?"


def _refusing(*refused: tuple[str | None, str]) -> Authorize:
    """A hook that refuses each ``(participant acted for, action)`` pair, and allows the rest."""

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        behalf = acting_for(actor)
        return (behalf and behalf.participant, access.action) not in refused

    return authorize


async def test_a_message_whose_author_may_not_start_a_turn_does_not_wedge_its_thread(
    storage: InMemoryStorage, gate: Gate, caplog: pytest.LogCaptureFixture
) -> None:
    workspaces = Workspaces(storage, authorize=_refusing(("user:bob", "artifactr:record")))
    ws = await workspaces.open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    script = Script(say("Hi Alice."))
    runner = make_runner(make_agent(script), gate)
    bob = ws.as_actor(BOB)
    with pytest.raises(Forbidden, match="artifactr:record is refused"):
        await runner.send(bob, thread.id, "Ship it")
    assert [e.event.type for e in await ws.read()] == ["thread_created"], "the sender is refused"
    await bob.post_message(thread.id, "Ship it")  # committed without the runner
    with caplog.at_level(logging.WARNING, logger="artifactr.agent"):
        await started(await runner.send(ws, thread.id, "Hello")).wait()
        await settled(thread.id, runner)
    assert await _for_whom(ws) == ["user:alice"], "Bob's message is passed over"
    assert script.prompt_texts(0)[-1] == "Hello"
    log = await ws.read()
    [notice] = [e for e in log if isinstance(e.event, MessagePosted) and e.event.kind == "notice"]
    assert notice.actor == SystemActor(name="runner"), "and people are told, by the runner"
    assert event_as(notice, MessagePosted).content == NOT_TAKEN
    assert "artifactr:record" not in event_as(notice, MessagePosted).content, "in their words"
    assert script.conversation() == ["Hello"], "the agent is not told the notice"
    [skipped] = [r for r in caplog.records if "skips a turn" in r.getMessage()]
    assert skipped.levelno == logging.WARNING
    assert "artifactr:record is refused" in skipped.getMessage(), "the log says why"


async def test_a_notice_the_runner_may_not_post_is_logged_and_the_turn_still_skipped(
    storage: InMemoryStorage, gate: Gate, caplog: pytest.LogCaptureFixture
) -> None:
    refused = _refusing(("user:bob", "artifactr:record"), (None, "artifactr:post_message"))
    ws = await Workspaces(storage, authorize=refused).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    script = Script(say("Hi Alice."))
    runner = make_runner(make_agent(script), gate)
    await ws.as_actor(BOB).post_message(thread.id, "Ship it")  # committed without the runner
    with caplog.at_level(logging.WARNING, logger="artifactr.agent"):
        await started(await runner.send(ws, thread.id, "Hello")).wait()
        await settled(thread.id, runner)
    assert await _for_whom(ws) == ["user:alice"], "Bob's message is still passed over"
    log = await ws.read()
    assert not [e for e in log if isinstance(e.event, MessagePosted) and e.event.kind == "notice"]
    [refusal] = [r.getMessage() for r in caplog.records if "notice" in r.getMessage()]
    assert refusal.endswith("artifactr:post_message is refused in this workspace")


async def test_a_reply_its_author_may_not_give_is_passed_over(
    storage: InMemoryStorage, gate: Gate
) -> None:
    workspaces = Workspaces(storage, authorize=_refusing(("user:bob", "artifactr:answer_deferred")))
    ws = await workspaces.open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    asking = [str, DeferredToolRequests]
    script = Script(ask("q1", "Which day?"), say("Monday."))
    runner = make_runner(make_agent(script, ask=True, output_type=asking), gate)
    await started(await runner.send(ws, thread.id, "Plan it")).wait()
    await ws.as_actor(BOB).post_message(thread.id, "Tuesday")  # Bob may not answer
    await started(await runner.send(ws, thread.id, "Monday")).wait()
    await settled(thread.id, runner)
    assert script.tool_returns(1) == ["Monday"], "Alice's message is the reply"


async def test_a_resume_its_answerer_may_not_start_ends_the_run(
    storage: InMemoryStorage, gate: Gate
) -> None:
    workspaces = Workspaces(storage, authorize=_refusing(("user:bob", "artifactr:record")))
    ws = await workspaces.open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    asking = [str, DeferredToolRequests]
    script = Script(ask("q1", "Which day?"), say("Hi Alice."))
    runner = make_runner(make_agent(script, ask=True, output_type=asking), gate)
    paused = started(await runner.send(ws, thread.id, "Plan it"))
    await paused.wait()
    answer = AnswerDeferred(run_id=paused.run_id, tool_call_id="q1", answer=in_words("Monday"))
    await ws.as_actor(BOB).commit(answer)  # Bob may answer, but not run the agent
    await started(await runner.send(ws, thread.id, "Hello")).wait()
    await settled(thread.id, runner)
    ended = await ws.run(paused.run_id)
    assert ended.status == "failed"
    [end] = [e.event for e in await ws.read() if isinstance(e.event, RunEnded)][:1]
    assert (end.reason, end.error) == ("forbidden", "artifactr:record is refused in this workspace")
    assert await _for_whom(ws) == ["user:alice", "user:alice"], "Alice's message runs next"


async def test_a_message_whose_ask_was_lost_is_taken_once_asked_again(
    storage: InMemoryStorage, gate: Gate
) -> None:
    workspaces = Workspaces(storage, authorize=_refusing(("user:bob", "artifactr:record")))
    ws = await workspaces.open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    script = Script(say("Hi Alice."))
    runner = make_runner(make_agent(script), gate)
    assert await runner.ask(ws, thread.id) is None, "nothing to take"
    await ws.post_message(thread.id, "Hello")  # committed, and the process stopped before asking
    with pytest.raises(Forbidden, match="artifactr:record is refused"):
        await runner.ask(ws.as_actor(BOB), thread.id)
    handle = await runner.ask(ws, thread.id)
    assert handle is not None
    await handle.wait()
    await settled(thread.id, runner)
    assert await _for_whom(ws) == ["user:alice"]
    assert script.prompt_texts(0)[-1] == "Hello"
    assert await runner.ask(ws, thread.id) is None, "taken, so nothing more to take"


async def test_ask_is_asked_as_the_agent_acting_for_its_caller_once(
    storage: InMemoryStorage, gate: Gate
) -> None:
    asked: list[tuple[Actor, str]] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        asked.append((actor, access.action))
        return True

    ws = await Workspaces(storage, authorize=authorize).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = make_runner(make_agent(Script()), gate)
    asked.clear()
    assert await runner.ask(ws, thread.id) is None
    records = [actor for actor, action in asked if action == "artifactr:record"]
    assert records == [AgentActor(thread_id=thread.id, on_behalf_of=ALICE)]
