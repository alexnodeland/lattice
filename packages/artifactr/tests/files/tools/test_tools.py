"""The agent's tools for native files, driven by a scripted model through artifactr's capability.

An edit that becomes a proposal, a busy file the agent plans around, a stale base it reads
again for, reads in pages, and the tools hidden in a workspace where the app is off.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    BinaryContent,
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolReturnPart,
)

from artifactr.agent import ArtifactWorkspace, Session
from artifactr.core import Thread, UserActor
from artifactr.files.app import AppCommand, AppFailed, FakeApp
from artifactr.files.blobs import InMemoryBlobs, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.manifest import DOCX, WordDocument
from artifactr.files.native import NativeFiles
from artifactr.files.tools import REVIEW_ITEMS, TEXT_CHARS, native_file_tools
from artifactr.workspace import ArtifactBusy, InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import Script, call, say
from tests.files.conftest import Switch

ALICE = UserActor(id="alice", name="Alice")
TOOLS = {"read_native", "read_review", "find_commands", "edit_native"}


def add(text: str) -> dict[str, Any]:
    """An `add_paragraph` command, as a model sends it."""
    return {"name": "add_paragraph", "args": {"text": text}}


def command(name: str, text: str) -> AppCommand:
    return AppCommand(name=name, args={"text": text})


@dataclass
class World:
    ws: Workspace
    thread: Thread
    files: NativeFiles
    switch: Switch
    app: FakeApp

    async def run(self, script: Script, *, view: bool = False) -> None:
        agent = Agent(
            script.model,
            deps_type=Session[None],
            toolsets=[native_file_tools(self.files, view=view)],
            capabilities=[ArtifactWorkspace(types=[WordDocument])],
        )
        await agent.run("Go.", deps=Session.start(self.ws, self.thread.id, app=None))


@pytest.fixture
async def world() -> World:
    switch, app = Switch(), FakeApp()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app, integrations=switch)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    upload = once(FakeApp.file("Terms", comments=["Check the dates"]))
    await files.upload(ws, WordDocument, "c.docx", upload, media_type=DOCX, artifact_id="a1")
    return World(ws, await ws.create_thread("Contract"), files, switch, app)


async def test_an_agents_edit_is_a_proposal_of_its_batch(world: World) -> None:
    script = Script(
        call(
            "edit_native", artifact_id="a1", base_version=1, commands=[add("Fees")], summary="Fees"
        ),
        say("Proposed."),
    )
    await world.run(script)
    [returned] = script.tool_returns(1)
    assert returned.startswith("Proposed as")
    [proposal] = await world.ws.proposals(status="pending")
    assert proposal.artifact_id == "a1"
    assert (await world.ws.get(WordDocument, "a1")).version == 1


async def test_a_busy_file_is_planned_around_not_retried(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    script = Script(
        call("edit_native", artifact_id="a1", base_version=1, commands=[add("Fees")], summary="x"),
        say("I'll wait."),
    )
    await world.run(script)
    [returned] = script.tool_returns(1)
    assert f"is checked out by user:alice until {checkout.expires_at.isoformat()}" in returned
    assert "plan again once it is checked in" in returned
    assert await world.ws.proposals(status="pending") == []


async def test_another_agents_edit_is_retried(world: World) -> None:
    await world.ws.lease_artifact("a1", holder="edit:other", ttl=timedelta(seconds=45))
    edit = call("edit_native", artifact_id="a1", base_version=1, commands=[add("x")], summary="x")
    script = Script(edit, say("Done."))
    await world.run(script)
    assert "is held by edit:other until" in _retry(script.requests[1])


async def test_a_lease_that_just_ended_is_retried_at_once(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def busy(*args: object, **kwargs: object) -> None:
        raise ArtifactBusy("a1", None)

    monkeypatch.setattr(world.files, "edit", busy)
    edit = call("edit_native", artifact_id="a1", base_version=1, commands=[add("x")], summary="x")
    script = Script(edit, say("Done."))
    await world.run(script)
    assert "its lease ended before it was read" in _retry(script.requests[1])


@pytest.mark.parametrize("tool", ["edit_native", "view_page"])
async def test_an_app_that_cant_finish_fails_the_call_not_retried(world: World, tool: str) -> None:
    args = (
        {"base_version": 1, "commands": [add("x")], "summary": "x"} if tool == "edit_native" else {}
    )
    script = Script(call(tool, artifact_id="a1", **args), say("Done."))
    world.app.fails = "timeout"
    with pytest.raises(AppFailed, match="timeout"):
        await world.run(script, view=True)


async def test_a_stale_base_is_read_again(world: World) -> None:
    applied = await world.files.edit(
        world.ws, "a1", base_version=1, commands=[command("add_paragraph", "Fees")], summary="Fees"
    )
    assert applied is not None
    stale = call("edit_native", artifact_id="a1", base_version=1, commands=[add("x")], summary="x")
    fresh = call(
        "edit_native", "call_2", artifact_id="a1", base_version=2, commands=[add("x")], summary="x"
    )
    script = Script(stale, fresh, say("Proposed."))
    await world.run(script)
    assert "Read the artifact again" in _retry(script.requests[1])
    assert script.tool_returns(2)[0].startswith("Proposed as")


async def test_a_command_the_app_refuses_is_retried_with_why(world: World) -> None:
    bad = {"name": "format_disk", "args": {}}
    script = Script(
        call("edit_native", artifact_id="a1", base_version=1, commands=[bad], summary="x"),
        say("Sorry."),
    )
    await world.run(script)
    assert "The app refused the batch: refused: format_disk" in _retry(script.requests[1])


async def test_a_batch_that_changes_nothing_says_so(world: World) -> None:
    script = Script(
        call("edit_native", artifact_id="a1", base_version=1, commands=[], summary="x"),
        say("Nothing to do."),
    )
    await world.run(script)
    assert script.tool_returns(1) == ["The batch changed nothing in the file."]


async def test_its_words_are_read_in_pages(world: World) -> None:
    long = "x" * (TEXT_CHARS + 10)
    await world.files.edit(
        world.ws, "a1", base_version=1, commands=[command("add_paragraph", long)], summary=""
    )
    script = Script(
        call("read_native", artifact_id="a1"),
        call("read_native", "call_2", artifact_id="a1", start=TEXT_CHARS),
        say("Read."),
    )
    await world.run(script)
    [first] = script.tool_returns(1)
    assert first.startswith("Terms\n\nxxx")
    assert first.endswith(f"[17 more characters: read on from start={TEXT_CHARS}]")
    assert script.tool_returns(2) == ["x" * 17]


async def test_its_review_is_read_in_pages_each_item_marked(world: World) -> None:
    script = Script(call("read_review", artifact_id="a1"), say("Read."))
    await world.run(script)
    assert script.tool_returns(1) == ['{"id": 0, "text": "Check the dates", "kind": "comment"}']


async def test_a_long_review_says_where_to_read_on(world: World) -> None:
    many = [command("add_comment", f"c{i}") for i in range(REVIEW_ITEMS)]
    await world.files.edit(world.ws, "a1", base_version=1, commands=many, summary="")
    script = Script(call("read_review", artifact_id="a1"), say("Read."))
    await world.run(script)
    [shown] = script.tool_returns(1)
    assert shown.endswith(f"[1 more: read on from start={REVIEW_ITEMS}]")


async def test_a_file_without_a_review_says_so(world: World) -> None:
    upload = once(FakeApp.file("Bare"))
    await world.files.upload(
        world.ws, WordDocument, "b.docx", upload, media_type=DOCX, artifact_id="b1"
    )
    script = Script(call("read_review", artifact_id="b1"), say("Read."))
    await world.run(script)
    assert script.tool_returns(1) == ["It has no comments or tracked changes."]


async def test_commands_are_found_by_a_word(world: World) -> None:
    script = Script(
        call("find_commands", query="comment"),
        call("find_commands", "call_2", query="nothing like it"),
        say("Found."),
    )
    await world.run(script)
    assert script.tool_returns(1) == ["- add_comment(text): Add a comment."]
    assert script.tool_returns(2) == ["No command mentions 'nothing like it': try another word."]


async def test_a_page_is_shown_only_if_the_application_turns_it_on(world: World) -> None:
    without, with_pages = Script(say("Done.")), Script(say("Done."))
    await world.run(without)
    await world.run(with_pages, view=True)
    assert _offered(without) == TOOLS
    assert _offered(with_pages) == {*TOOLS, "view_page"}


async def test_a_page_is_an_image_and_a_missing_one_is_retried(world: World) -> None:
    script = Script(
        call("view_page", artifact_id="a1"),
        call("view_page", "call_2", artifact_id="a1", page=9),
        say("Seen."),
    )
    await world.run(script, view=True)
    request = script.requests[1][-1]
    assert isinstance(request, ModelRequest)
    [page] = [p.content for p in request.parts if isinstance(p, ToolReturnPart)]
    assert isinstance(page, BinaryContent)
    assert page.media_type == "image/png"
    assert page.data.startswith(b"\x89PNG")
    assert "The app can't show that page" in _retry(script.requests[2])


async def test_switched_off_the_tools_are_not_offered(world: World) -> None:
    world.switch.off.add(("acme", "w1", "files:fake"))
    script = Script(say("Done."))
    await world.run(script, view=True)
    assert _offered(script) == set()


def _offered(script: Script) -> set[str]:
    """The native tools the model was first offered."""
    return {t.name for t in script.infos[0].function_tools} & {*TOOLS, "view_page"}


def _retry(messages: list[ModelMessage]) -> str:
    """What the model was told to retry with, in a request."""
    last = messages[-1]
    assert isinstance(last, ModelRequest)
    return " ".join(str(p.content) for p in last.parts if isinstance(p, RetryPromptPart))
