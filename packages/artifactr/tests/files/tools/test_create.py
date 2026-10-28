"""`create_native_file`, driven by a scripted model: a blank file of every type the workspace may
create, which the agent then edits, offered only for the types whose app is on, and every
refusal told in a sentence.
"""

from collections.abc import Iterator, Sequence

import pytest
from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.capabilities import AbstractCapability, Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import Actor, SetThreadMode, Thread, UserActor, artifact_types
from artifactr.files.app import AppCommand, AppFailed, FakeApp
from artifactr.files.app import Applied as Made
from artifactr.files.blobs import InMemoryBlobs, Quota
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.manifest import DXF, Drawing, NativeFile, WordDocument
from artifactr.files.native import NativeFiles, Pace
from artifactr.files.tools import native_file_tools
from artifactr.files.tools.tools import _call_id
from artifactr.telemetry.attributes import ACTOR_KIND, ARTIFACT_ID, RUN_ID, USER_ID
from artifactr.workspace import Access, Authorize, InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import Script, call, say
from tests.files.conftest import Switch
from tests.files.naming import Naming
from tests.telemetry.conftest import Recorder, attributes, recording

ALICE = UserActor(id="alice", name="Alice")
RUN = "run_1"
TYPES = {k: t for k, t in sorted(artifact_types().items()) if issubclass(t, NativeFile)}
"""Every native type, by kind."""


@pytest.fixture
def recorder() -> Iterator[Recorder]:
    yield from recording()


async def opened(authorize: Authorize | None = None) -> tuple[Workspace, Thread]:
    ws = await Workspaces(InMemoryStorage(), authorize=authorize).open("acme", "w1", actor=ALICE)
    return ws, await ws.create_thread("Trip")


async def run(
    files: NativeFiles,
    ws: Workspace,
    thread: Thread,
    script: Script,
    *,
    person: UserActor | None = ALICE,
    recorder: Recorder | None = None,
) -> None:
    capabilities: list[AbstractCapability[Session[None]]] = [
        ArtifactWorkspace(types=[WordDocument])
    ]
    if recorder is not None:
        settings = InstrumentationSettings(**recorder.providers)
        capabilities.append(Instrumentation(settings=settings))
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[native_file_tools(files)],
        capabilities=capabilities,
    )
    deps = Session.start(ws, thread.id, app=None, run_id=RUN, on_behalf_of=person)
    await agent.run("Go.", deps=deps)


def create(
    kind: str = "word_document", title: str = "Trip", call_id: str = "call_1"
) -> ModelResponse:
    return call("create_native_file", call_id, type=kind, title=title)


def edit_what_was_created(messages: list[ModelMessage]) -> ModelResponse:
    """Edit the file the last call created, by the id its result named."""
    created = _returned(messages).removeprefix("Created ").split(":")[0]
    add = {"name": "add_paragraph", "args": {"text": "Day one"}}
    return call("edit_native", artifact_id=created, base_version=1, commands=[add], summary="Day")


def refusing(action: str) -> Authorize:
    """An `authorize` that refuses one action to the agent: a tenant's narrowing."""

    async def authorize(_t: str, _w: str | None, actor: Actor, access: Access) -> bool:
        return not (actor.kind == "agent" and access.action == action)

    return authorize


@pytest.mark.parametrize("kind", TYPES)
async def test_every_type_is_created_blank_and_then_edited_by_proposal(kind: str) -> None:
    apps = {NativeFile: FakeApp(), Drawing: Naming(DXF)}
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), apps)
    ws, thread = await opened()
    script = Script(create(kind), edit_what_was_created, say("Done."))
    await run(files, ws, thread, script)
    [file] = await ws.artifacts(NativeFile)
    name = (await ws.get(NativeFile, file.id)).data.name
    noun = TYPES[kind].noun or f"a {kind.replace('_', ' ')}"
    assert script.tool_returns(1) == [
        f"Created {file.id}: {noun} named {name}, at version 1. "
        "It is empty: edit it with edit_native. An edit that is proposed waits for a "
        "person's review, and the file stays empty until it is accepted, so tell the person "
        "it waits for review."
    ]
    assert script.tool_returns(2)[0].startswith("Proposed as ")
    assert (file.kind, file.version) == (kind, 1), "the edit waits for review"
    assert file.id in (await ws.thread(thread.id)).focus, "the agent is told of changes to it"


async def test_only_the_types_whose_app_is_on_are_offered_and_created() -> None:
    switch = Switch(off={("acme", "w1", "files:wordcraft")})
    apps = {NativeFile: FakeApp(), WordDocument: FakeApp(integration="files:wordcraft")}
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), apps, integrations=switch)
    ws, thread = await opened()
    script = Script(create("word_document"), say("Done."))
    await run(files, ws, thread, script)
    [tool] = [t for t in script.infos[0].function_tools if t.name == "create_native_file"]
    offered = tool.parameters_json_schema["properties"]["type"]["enum"]
    assert "word_document" not in offered
    assert "presentation" in offered
    assert "- presentation (.pptx): a presentation" in (tool.description or "")
    assert "word_document" not in (tool.description or "")
    assert script.tool_returns(1) == [
        "'word_document' can't be created in this workspace: create one of the types listed."
    ]
    assert await ws.artifacts(NativeFile) == []


async def test_a_run_for_no_one_proposes_the_file() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    script = Script(create(), say("Done."))
    await run(files, ws, thread, script, person=None)
    assert script.tool_returns(1)[0].startswith("Proposed as ")


async def test_the_file_is_marked_on_its_tools_span(recorder: Recorder) -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    await run(files, ws, thread, Script(create(), say("Done.")), recorder=recorder)
    [file] = await ws.artifacts(NativeFile)
    [span] = [s for s in recorder.spans() if s.name == "execute_tool create_native_file"]
    marked = attributes(span)
    assert marked[ARTIFACT_ID] == file.id
    assert marked[USER_ID] == "alice", "the person it is committed as"
    assert (marked[ACTOR_KIND], marked[RUN_ID]) == ("agent", RUN), "and the agent's run that asked"


@pytest.mark.parametrize(
    ("app", "readings", "told"),
    [
        (
            FakeApp(fails="crashed"),
            None,
            "The app that makes a Word document is unavailable now: crashed: the fake app was "
            "told to fail.",
        ),
        (
            Naming(blank=False),
            None,
            "The app can't make a Word document from nothing: refused: it makes no file from "
            "nothing.",
        ),
        (
            FakeApp(),
            0,
            "A Word document wasn't created: 0 of the tenant's files are being read: try again "
            "shortly.",
        ),
    ],
    ids=["a-worker-crashed", "a-craft-with-no-blank-file", "busy"],
)
async def test_an_app_that_cant_make_it_is_told(
    app: FakeApp, readings: int | None, told: str
) -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app, readings=readings)
    ws, thread = await opened()
    script = Script(create(), say("Done."))
    await run(files, ws, thread, script)
    assert script.tool_returns(1) == [told]


@pytest.mark.parametrize("action", ["artifactr:create_native_file", "artifactr:create_artifact"])
async def test_a_tenant_that_narrows_creation_away_is_told(action: str) -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened(refusing(action))
    script = Script(create(), say("Done."))
    await run(files, ws, thread, script)
    assert script.tool_returns(1) == [
        f"You may not create a Word document here: {action} is refused in this workspace."
    ]


async def test_a_workspace_past_its_quota_is_told() -> None:
    blobs = InMemoryBlobs(workspace_quota=Quota(files=0))
    files = NativeFiles(blobs, InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    script = Script(create(), say("Done."))
    await run(files, ws, thread, script)
    assert script.tool_returns(1) == [
        "A Word document wasn't created: the workspace files quota of 0 would be passed."
    ]


async def test_an_agent_past_its_pace_is_told_when_to_try_again() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp(), pace=Pace(1))
    ws, thread = await opened()
    script = Script(create(title="One"), create(title="Two", call_id="call_2"), say("Done."))
    await run(files, ws, thread, script)
    [paced] = script.tool_returns(2)
    assert paced.startswith("A Word document wasn't created: too many files are being made: ")
    assert "try again in" in paced
    assert len(await ws.artifacts(NativeFile)) == 1


def _returned(messages: list[ModelMessage]) -> str:
    last = messages[-1]
    assert isinstance(last, ModelRequest)
    [part] = [p for p in last.parts if isinstance(p, ToolReturnPart)]
    return str(part.content)


class Pageless(FakeApp):
    """A fake app whose blank file has no page, and which renders none, as FilmCraft's,
    EffectCraft's and SoundCraft's blank projects."""

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Made:
        applied = await super().apply(source, commands, deadline=deadline)
        return Made(applied.content, applied.inspection.model_copy(update={"pages": 0}))

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        raise AppFailed("refused", f"no page {page}")


async def test_a_blank_project_with_no_page_is_still_created() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Pageless())
    ws, thread = await opened()
    script = Script(create("video_project"), say("Done."))
    await run(files, ws, thread, script)
    [file] = await ws.artifacts(NativeFile)
    assert script.tool_returns(1)[0].startswith(f"Created {file.id}: a video project named")
    assert (await ws.get(NativeFile, file.id)).data.pages == 0


async def test_a_worker_past_its_deadline_is_told() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp(fails="timeout"))
    ws, thread = await opened()
    script = Script(create(), say("Done."))
    await run(files, ws, thread, script)
    assert script.tool_returns(1)[0].startswith(
        "The app that makes a Word document is unavailable now: timeout:"
    )


async def test_a_call_retried_makes_one_file_and_spends_no_pace_or_quota() -> None:
    blobs = InMemoryBlobs(workspace_quota=Quota(files=1))
    files = NativeFiles(blobs, InMemoryCheckouts(), FakeApp(), pace=Pace(1))
    ws, thread = await opened()
    script = Script(create(), create(), say("Done."))
    await run(files, ws, thread, script)
    [file] = await ws.artifacts(NativeFile)
    first, again = script.tool_returns(1)[0], script.tool_returns(2)[0]
    assert first == again
    assert first.startswith(f"Created {file.id}: ")


async def test_a_run_creates_only_so_many_files() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    script = Script(*(create(title=f"T{i}", call_id=f"c{i}") for i in range(3)), say("Done."))
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[native_file_tools(files, creates=2)],
        capabilities=[ArtifactWorkspace(types=[WordDocument])],
    )
    await agent.run("Go.", deps=Session.start(ws, thread.id, app=None, on_behalf_of=ALICE))
    assert script.tool_returns(3) == [
        "You have created 2 files in this run: create no more until asked."
    ]
    assert len(await ws.artifacts(NativeFile)) == 2


async def test_a_hostile_title_is_kept_as_a_safe_name() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    title = "../../etc/pa\x07ss\u202ewd\\" + "é" * 400 + ".exe"
    await run(files, ws, thread, Script(create(title=title), say("Done.")))
    [file] = await ws.artifacts(NativeFile)
    name = (await ws.get(NativeFile, file.id)).data.name
    assert name.endswith(".docx")
    assert not any(c in name for c in "/\\\x07\u202e")
    assert len(name) <= 200


async def test_the_run_isnt_told_of_its_own_file_as_its_persons() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    script = Script(create(), say("Done."))
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[native_file_tools(files)],
        capabilities=[ArtifactWorkspace(types=[WordDocument])],
    )
    runner = Runner(agent, app=None)
    handle = (await runner.send(ws, thread.id, "Make a document")).run
    assert handle is not None
    await handle.wait()
    await runner.drain()
    told = [
        part.content
        for message in script.requests[1]
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    assert told == ["Make a document"], "the tool's answer is all it hears of its file"


async def test_refused_attempts_spend_none_of_the_runs_files() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp(fails="crashed"))
    ws, thread = await opened()
    script = Script(*(create(call_id=f"c{i}") for i in range(3)), say("Done."))
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[native_file_tools(files, creates=1)],
        capabilities=[ArtifactWorkspace(types=[WordDocument])],
    )
    await agent.run("Go.", deps=Session.start(ws, thread.id, app=None, on_behalf_of=ALICE))
    for request in (1, 2, 3):
        assert script.tool_returns(request)[0].startswith("The app that makes a Word document")


def test_a_call_without_an_id_is_never_taken_for_a_retry() -> None:
    assert _call_id("r1", None) != _call_id("r1", None)
    assert _call_id("r1", "c1") == _call_id("r1", "c1")


async def test_a_suggest_threads_blank_file_is_made_and_its_edit_held() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    await ws.commit(SetThreadMode(thread_id=thread.id, mode="suggest"))
    script = Script(create(), edit_what_was_created, say("Done."))
    await run(files, ws, thread, script)
    assert script.tool_returns(1)[0].startswith("Created ")
    assert script.tool_returns(2)[0].startswith("Proposed as ")


async def test_a_run_for_no_one_retried_proposes_again() -> None:
    """A limit: a proposal isn't a file, so a retried call for no one is proposed twice."""
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened()
    script = Script(create(), create(), say("Done."))
    await run(files, ws, thread, script, person=None)
    assert len(await ws.proposals(status="pending")) == 2


async def test_a_retry_refused_still_counts_the_file_it_made() -> None:
    refused: set[str] = set()

    async def authorize(_t: str, _w: str | None, actor: Actor, access: Access) -> bool:
        return not (actor.kind == "agent" and access.action in refused)

    def then_refuse(messages: list[ModelMessage]) -> ModelResponse:
        refused.add("artifactr:create_native_file")
        return create()

    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws, thread = await opened(authorize)
    script = Script(create(), then_refuse, create(call_id="c2"), say("Done."))
    agent = Agent(
        script.model,
        deps_type=Session[None],
        toolsets=[native_file_tools(files, creates=1)],
        capabilities=[ArtifactWorkspace(types=[WordDocument])],
    )
    await agent.run("Go.", deps=Session.start(ws, thread.id, app=None, on_behalf_of=ALICE))
    assert script.tool_returns(2)[0].startswith("You may not create")
    assert script.tool_returns(3) == [
        "You have created 1 files in this run: create no more until asked."
    ]
