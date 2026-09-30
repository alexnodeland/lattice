"""Notices: messages for people, which start, steer and answer no turn (ADR-0051)."""

import asyncio

import pytest
from pydantic_ai import DeferredToolRequests, FunctionToolset, ModelRequest, UserPromptPart

from artifactr.agent import Session, load_history
from artifactr.core import ExternalAgentActor, PostMessage, Recorded, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import (
    Gate,
    Script,
    call,
    make_agent,
    make_runner,
    say,
    settle,
    started,
    types,
)

RULE = ExternalAgentActor(client_id="reflexr:timeline-entry", name="timeline-entry")
TOLD = (
    "<workspace-changes>\n- timeline-entry posted a notice: The rule is live\n</workspace-changes>"
)


def notice(thread_id: str) -> PostMessage:
    return PostMessage(thread_id=thread_id, content="The rule is live", kind="notice")


async def test_a_notice_starts_no_turn(ws: Workspace, thread: Thread, gate: Gate) -> None:
    runner = make_runner(make_agent(Script()), gate)
    posted = await runner.execute(ws.as_actor(RULE), notice(thread.id), command_id="c1")
    assert posted.outcome == Recorded(seq=2)
    assert runner.running(thread.id) is None
    assert types(await ws.read()) == ["thread_created", "message_posted"]


async def test_a_notice_answers_no_paused_run(ws: Workspace, thread: Thread, gate: Gate) -> None:
    script = Script(call("ask_user", call_id="q1", question="Which day?"))
    agent = make_agent(script, ask=True, output_type=[str, DeferredToolRequests])
    runner = make_runner(agent, gate)
    handle = started(await runner.send(ws, thread.id, "Plan the launch"))
    await handle.wait()
    await runner.execute(ws.as_actor(RULE), notice(thread.id), command_id="c1")
    run = await ws.run(handle.run_id)
    assert (run.status, run.answers) == ("paused", {})
    assert runner.running(thread.id) is None


@pytest.mark.parametrize("notices", [False, True])
async def test_a_notice_during_a_turn_is_passed_into_it_only_as_a_note_asked_for(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    app_tools: FunctionToolset[Session[Gate]],
    notices: bool,
) -> None:
    script = Script(call("hold"), say("Done."))
    runner = make_runner(make_agent(script, tools=[app_tools], notices=notices), gate)
    handle = started(await runner.send(ws, thread.id, "Plan the launch"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    await runner.execute(ws.as_actor(RULE), notice(thread.id), command_id="c1")
    await settle()
    gate.release.set()
    await handle.wait()
    assert script.prompt_texts(1) == ["Plan the launch", *([TOLD] if notices else [])]


@pytest.mark.parametrize("notices", [False, True])
async def test_a_notice_is_in_the_agents_history_only_when_asked(
    ws: Workspace, thread: Thread, gate: Gate, notices: bool
) -> None:
    rule = ws.as_actor(RULE)
    await rule.commit(notice(thread.id))
    await rule.commit(notice((await ws.create_thread("Elsewhere")).id))
    runner = make_runner(make_agent(Script(say("Noted.")), notices=notices), gate)
    await started(await runner.send(ws, thread.id, "What's new?")).wait()
    prompts = [
        part.content
        for message in await load_history(ws, thread.id)
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    assert prompts == ["What's new?", *([TOLD] if notices else [])], "only this thread's"
