"""A run's life in the workspace: what is recorded, what the agent is told, and history."""

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelRequest

from artifactr.agent import Session, last_seen, load_history
from artifactr.core import AgentActor, RunEnded, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import (
    Gate,
    Script,
    call,
    event_as,
    make_agent,
    make_runner,
    say,
    started,
    types,
)
from tests.artifact_types import Note


async def test_a_message_starts_a_recorded_run(ws: Workspace, thread: Thread, gate: Gate) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"title": "Plan", "text": "Ship Friday"}),
        say("I drafted the plan."),
    )
    runner = make_runner(make_agent(script), gate)
    handle = (await runner.send(ws, thread.id, "Draft a plan")).run
    assert handle is not None
    assert runner.running(thread.id) == handle
    result = await handle.wait()
    assert result.output == "I drafted the plan."
    assert runner.running(thread.id) is None
    log = await ws.read()
    assert types(log) == [
        "thread_created",
        "message_posted",
        "run_started",
        "tool_called",
        "artifact_created",
        "focus_changed",
        "tool_returned",
        "message_posted",
        "run_ended",
    ]
    agent = AgentActor(thread_id=thread.id, run_id=handle.run_id)
    assert [e.actor for e in log[2:]] == [agent] * 7
    [note] = await ws.artifacts(Note)
    assert note.updated_by == agent
    run = await ws.run(handle.run_id)
    assert run.status == "completed"
    ended = log[-1].event
    assert isinstance(ended, RunEnded)
    assert ended.usage is not None
    assert ended.usage.requests == 2
    assert "Ship Friday" in script.instructions(1), "followed artifacts are rendered"
    assert await last_seen(ws, thread.id) == log[-1].seq


async def test_the_next_run_continues_the_conversation(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("Hello!"), say("Still here."))
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Hi")).wait()
    await started(await runner.send(ws, thread.id, "Are you there?")).wait()
    assert script.prompt_texts(1) == ["Hi", "Are you there?"]
    history = await load_history(ws, thread.id)
    assert len(history) == 4


async def test_the_agent_is_told_what_changed_since_it_last_looked(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"text": "Ship Friday"}),
        say("Drafted."),
        say("Noted."),
    )
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Draft")).wait()
    [note] = await ws.artifacts(Note)
    await ws.commit(note.edit_text("Friday", "Monday"))
    await started(await runner.send(ws, thread.id, "I moved the date")).wait()
    notes = [text for text in script.prompt_texts(2) if "<workspace-changes>" in text]
    assert notes == [
        f"<workspace-changes>\n- Alice changed {note.id} (note, v1 → v2): "
        "edited text (1 replacement)\n</workspace-changes>"
    ]


async def test_instructions_describe_the_workspace(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    await ws.create(Note(text="x" * 5000), artifact_id="n1")
    from artifactr.core import SetFocus, SetThreadMode

    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("n1",)))
    await ws.commit(SetThreadMode(thread_id=thread.id, mode="suggest"))
    await ws.commit((await ws.get(Note, "n1")).archive())
    script = Script(say("ok"))
    agent = make_agent(script)
    await agent.run("hi", deps=Session.start(ws, thread.id, app=gate))
    instructions = script.instructions(0)
    assert "suggest mode" in instructions
    assert "Kinds of artifact you can create: note, checklist." in instructions
    assert '<artifact id="n1" kind="note" version="2" archived>' in instructions
    assert "x" * 3999 + "…" in instructions


async def test_a_direct_run_watches_from_its_own_start(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("ok"))
    session = Session.start(ws, thread.id, app=gate, agent_name="Scribe")
    await make_agent(script).run("hi", deps=session)
    [posted] = [e for e in await ws.read() if e.event.type == "message_posted"]
    assert posted.actor == AgentActor(thread_id=thread.id, run_id=session.run_id, name="Scribe")
    assert session.trigger == "api"


async def test_structured_or_empty_outputs_post_no_message(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    class Summary(BaseModel):
        points: list[str]

    script = Script(call("final_result", points=["a"]))
    agent = make_agent(script, output_type=Summary)
    result = await agent.run("summarize", deps=Session.start(ws, thread.id, app=gate))
    assert result.output == Summary(points=["a"])
    empty = Script(say("  "))
    await make_agent(empty).run("hi", deps=Session.start(ws, thread.id, app=gate))
    assert "message_posted" not in types(await ws.read())


async def test_a_failed_run_is_recorded(ws: Workspace, thread: Thread, gate: Gate) -> None:
    def fail(messages: object) -> None:
        raise RuntimeError("model unavailable")

    runner = make_runner(make_agent(Script(fail)), gate)  # type: ignore[arg-type]
    handle = (await runner.send(ws, thread.id, "hi")).run
    assert handle is not None
    with pytest.raises(RuntimeError):
        await handle.wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.error) == ("failed", "model unavailable")


async def test_an_unwatched_failure_does_not_warn(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    def fail(messages: object) -> None:
        raise RuntimeError("boom")

    runner = make_runner(make_agent(Script(fail)), gate)  # type: ignore[arg-type]
    handle = (await runner.send(ws, thread.id, "hi")).run
    assert handle is not None
    while not handle.task.done():
        await gate_sleep()
    assert runner.running(thread.id) is None


async def gate_sleep() -> None:
    import asyncio

    await asyncio.sleep(0.01)


def test_history_messages_are_model_requests_first() -> None:
    assert ModelRequest.kind == "request"
