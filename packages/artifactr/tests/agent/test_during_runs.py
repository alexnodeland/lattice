"""What happens while a run is in progress: steering, others' changes, and rejected tool calls."""

import asyncio
from typing import Any

import pytest
from pydantic_ai import FunctionToolset, ModelRequest, RunContext

from artifactr.agent import Session
from artifactr.core import EditArtifact, SetFocus, SetThreadMode, TextEdit, TextEdits, Thread
from artifactr.workspace import Workspace
from tests.agent.conftest import Gate, Script, call, make_agent, make_runner, say, types
from tests.artifact_types import Note


async def _started(gate: Gate) -> None:
    await asyncio.wait_for(gate.entered.wait(), timeout=2)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_message_during_a_run_steers_it(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    script = Script(call("hold"), say("Switching to Monday."))
    runner = make_runner(make_agent(script, tools=[app_tools]), gate)
    handle = await runner.send(ws, thread.id, "Plan the launch for Friday")
    assert handle is not None
    await _started(gate)
    assert await runner.send(ws, thread.id, "Actually, make it Monday") is None
    await _settle()
    gate.release.set()
    await handle.wait()
    assert script.prompt_texts(1)[-1] == "Actually, make it Monday"


async def test_others_changes_during_a_run_are_delivered(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("n1",)))
    script = Script(call("read_artifact", artifact_id="n1"), call("hold", call_id="c2"), say("ok"))
    runner = make_runner(make_agent(script, tools=[app_tools]), gate)
    handle = await runner.send(ws, thread.id, "Review the plan")
    assert handle is not None
    await _started(gate)
    await ws.commit((await ws.get(Note, "n1")).edit_text("Friday", "Monday"))
    await ws.create(Note(text="elsewhere"), artifact_id="n2")  # not followed: not delivered
    await _settle()
    gate.release.set()
    await handle.wait()
    briefing, during = [t for t in script.prompt_texts(2) if t.startswith("<workspace-changes>")]
    assert "Alice created n1 (note, v1)" in briefing, "at the start: what happened before"
    assert "Alice changed n1 (note, v1 → v2)" in during, "during: the edit, but not n2"


async def test_a_rejected_tool_call_becomes_a_retry(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    script = Script(
        call("edit_text", artifact_id="n1", old="Sunday", new="Monday"),
        call("edit_text", call_id="c2", artifact_id="n1", old="Friday", new="Monday"),
        say("Fixed."),
    )
    session = Session.start(ws, thread.id, app=gate)
    await make_agent(script).run("move it", deps=session)
    retry = _retry_text(script.requests[1])
    assert "the anchor 'Sunday' is not found" in retry
    log = await ws.read()
    statuses = [e.event.status for e in log if e.event.type == "tool_returned"]  # type: ignore[union-attr]
    assert statuses == ["retry", "ok"]
    assert (await ws.get(Note, "n1")).data.text == "Ship Monday"


async def test_a_version_conflict_tells_the_agent_to_read_again(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    await ws.create(Note(text="a"), artifact_id="n1")
    await ws.commit((await ws.get(Note, "n1")).edit_text("a", "b"))
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def stale_edit(ctx: RunContext[Session[Gate]]) -> str:
        patch = TextEdits(edits=(TextEdit(old="b", new="c"),))
        await ctx.deps.workspace.commit(EditArtifact(artifact_id="n1", base_version=1, patch=patch))
        return "unreachable"

    script = Script(call("stale_edit"), say("I'll read it first."))
    await make_agent(script, tools=[tools]).run("edit", deps=Session.start(ws, thread.id, app=gate))
    assert "Read the artifact again, then retry." in _retry_text(script.requests[1])


async def test_a_tool_failure_fails_the_run(ws: Workspace, thread: Thread, gate: Gate) -> None:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def broken(ctx: RunContext[Session[Gate]]) -> str:
        raise ValueError("disk full")

    script = Script(call("broken"))
    with pytest.raises(ValueError, match="disk full"):
        await make_agent(script, tools=[tools]).run(
            "go", deps=Session.start(ws, thread.id, app=gate)
        )
    log = await ws.read()
    returned = next(e.event for e in log if e.event.type == "tool_returned")
    assert (returned.status, returned.summary) == ("error", "ValueError: disk full")  # type: ignore[union-attr]
    assert log[-1].event.status == "failed"  # type: ignore[union-attr]


async def test_in_suggest_mode_edits_become_proposals(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    await ws.commit(SetThreadMode(thread_id=thread.id, mode="suggest"))
    script = Script(
        call("edit_text", artifact_id="n1", old="Friday", new="Monday", summary="moved"),
        say("Proposed."),
    )
    await make_agent(script).run("move it", deps=Session.start(ws, thread.id, app=gate))
    [proposal] = await ws.proposals()
    assert proposal.artifact_id == "n1"
    assert f"Proposed as {proposal.id}" in _tool_return(script.requests[1])
    assert f"Your proposals awaiting review: {proposal.id} (for n1)." in script.instructions(1)


async def test_the_agent_can_propose_explicitly(ws: Workspace, thread: Thread, gate: Gate) -> None:
    await ws.create(Note(text="Ship Friday"), artifact_id="n1")
    script = Script(
        call(
            "edit_text",
            artifact_id="n1",
            old="Friday",
            new="Monday",
            propose=True,
            rationale="safer",
        ),
        say("Proposed."),
    )
    await make_agent(script).run("suggest", deps=Session.start(ws, thread.id, app=gate))
    [proposal] = await ws.proposals()
    assert proposal.rationale == "safer"
    assert (await ws.get(Note, "n1")).version == 1


async def test_listing_reading_and_archiving(ws: Workspace, thread: Thread, gate: Gate) -> None:
    script = Script(
        call("list_artifacts"),
        call("create_artifact", call_id="c2", kind="note", data={"text": "Hi"}),
        call("list_artifacts", call_id="c3", kind="note"),
        call("list_artifacts", call_id="c4", kind="checklist"),
        lambda messages: call("archive_artifact", call_id="c5", artifact_id=_created_id(messages)),
        lambda messages: call("read_artifact", call_id="c6", artifact_id=_created_id(messages)),
        say("done"),
    )
    await make_agent(script).run("tidy", deps=Session.start(ws, thread.id, app=gate))
    returns = [_tool_return(script.requests[i]) for i in range(1, 7)]
    assert returns[0] == "There are no artifacts yet."
    assert returns[2].startswith("- art_")
    assert "(note, v1)" in returns[2]
    assert returns[3] == "There are no artifacts yet."
    assert returns[4].endswith("is now at version 2.")
    assert "(archived)" in returns[5]
    assert returns[5].endswith("Hi")
    assert types(await ws.read()).count("focus_changed") == 1, "following is idempotent"


def _created_id(messages: list[Any]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if part.part_kind == "tool-return" and str(part.content).startswith("Done: art_"):
                    return str(part.content).split()[1]
    raise AssertionError("no artifact was created")


def _tool_return(messages: list[Any]) -> str:
    last = messages[-1]
    assert isinstance(last, ModelRequest)
    return str(next(p.content for p in last.parts if p.part_kind == "tool-return"))


def _retry_text(messages: list[Any]) -> str:
    last = messages[-1]
    assert isinstance(last, ModelRequest)
    return str(next(p.content for p in last.parts if p.part_kind == "retry-prompt"))


async def test_creating_a_proposal_policy_type_proposes(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(call("create_artifact", kind="checklist", data={"title": "Beta"}), say("ok"))
    await make_agent(script).run("start a checklist", deps=Session.start(ws, thread.id, app=gate))
    [proposal] = await ws.proposals()
    assert proposal.change.type == "create_artifact"
    assert (await ws.thread(thread.id)).focus == (), "nothing to follow until it exists"
