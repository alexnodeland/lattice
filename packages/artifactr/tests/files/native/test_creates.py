"""A blank native file an agent creates: made by its app from nothing, applied for the person its
run acts for while its edits stay proposals, checked as the agent first, and paced, held to its
places and to quotas as an upload is.
"""

import pytest

from artifactr.core import (
    Actor,
    AgentActor,
    Applied,
    ExternalAgentActor,
    Forbidden,
    NotEnabled,
    Proposed,
    UserActor,
    ValidationFailed,
)
from artifactr.files.app import AppCommand, AppFailed
from artifactr.files.blobs import InMemoryBlobs, OverQuota, Quota, TooLarge
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.manifest import DOCX, DWG, DXF, Drawing, NativeFile, WordDocument
from artifactr.files.native import FORMATS, Busy, Format, Gauge, NativeFiles, Pace, Paced
from artifactr.workspace import Access, Authorize, InMemoryStorage, Workspace, Workspaces
from tests.files.conftest import Stores, Switch
from tests.files.naming import Naming

ALICE = UserActor(id="alice", name="Alice")
AGENT = AgentActor(thread_id="t1", run_id="r1", on_behalf_of=ALICE)


def refusing(action: str, kind: str = "agent") -> Authorize:
    """An `authorize` that refuses one action to one kind of actor."""

    async def authorize(_t: str, _w: str | None, actor: Actor, access: Access) -> bool:
        return not (actor.kind == kind and access.action == action)

    return authorize


async def workspace(actor: Actor = AGENT, authorize: Authorize | None = None) -> Workspace:
    workspaces = Workspaces(InMemoryStorage(), authorize=authorize)
    return await workspaces.open("acme", "w1", actor=actor)


async def test_an_agents_file_is_applied_for_its_person_and_its_edit_proposed(
    stores: Stores,
) -> None:
    ws, app = await workspace(), Naming()
    files = NativeFiles(stores.blobs, stores.checkouts, app)
    made = await files.create(ws, WordDocument, "../Travel plan", thread_id="t1")
    assert isinstance(made, Applied)
    assert made.version == 1
    head = await ws.get(WordDocument, made.artifact_id)
    assert (head.data.name, head.data.content.media_type) == ("Travel plan.docx", DOCX)
    provenance = head.data.provenance
    assert (provenance.source, provenance.app, provenance.base) == ("blank", "fake", None)
    assert (await ws.revisions(made.artifact_id))[0].actor == ALICE
    assert await files.read(ws, made.artifact_id, part="text") == b""
    edit = [AppCommand(name="add_paragraph", args={"text": "Day one"})]
    edited = await files.edit(ws, made.artifact_id, base_version=1, commands=edit, summary="Day")
    assert isinstance(edited, Proposed)


async def test_a_person_creates_one_directly_too() -> None:
    ws, files = await workspace(ALICE), NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming())
    assert isinstance(await files.create(ws, WordDocument, "Notes"), Applied)


@pytest.mark.parametrize(
    "agent",
    [
        AgentActor(thread_id="t1"),
        AgentActor(thread_id="t1", on_behalf_of=ExternalAgentActor(client_id="cli")),
        ExternalAgentActor(client_id="cli", on_behalf_of=ALICE),
    ],
    ids=["a-run-for-no-one", "a-run-for-a-client", "a-client"],
)
async def test_an_agent_acting_for_no_person_proposes_it_by_the_policy(agent: Actor) -> None:
    ws = await workspace(agent)
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming())
    assert isinstance(await files.create(ws, WordDocument, "Notes"), Proposed)


@pytest.mark.parametrize("action", ["artifactr:create_native_file", "artifactr:create_artifact"])
async def test_the_agent_is_checked_before_the_app_is_called(action: str) -> None:
    ws, app = await workspace(authorize=refusing(action)), Naming()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app)
    with pytest.raises(Forbidden):
        await files.create(ws, WordDocument, "Notes")
    assert app.made == 0


async def test_the_person_it_is_committed_as_is_checked_too() -> None:
    ws = await workspace(authorize=refusing("artifactr:create_artifact", kind="user"))
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming())
    with pytest.raises(Forbidden):
        await files.create(ws, WordDocument, "Notes")
    assert await ws.artifacts(NativeFile) == []


async def test_a_type_whose_app_is_off_is_refused() -> None:
    switch = Switch(off={("acme", "w1", "files:fake")})
    ws, app = await workspace(), Naming()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app, integrations=switch)
    with pytest.raises(NotEnabled):
        await files.create(ws, WordDocument, "Notes")
    assert app.made == 0


async def test_an_app_that_makes_no_blank_file_commits_nothing() -> None:
    ws = await workspace()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming(blank=False))
    with pytest.raises(AppFailed, match="refused"):
        await files.create(ws, WordDocument, "Notes")
    assert await ws.artifacts(NativeFile) == []


async def test_a_type_of_several_formats_takes_the_one_the_app_names() -> None:
    ws = await workspace(ALICE)
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming(DWG))
    made = await files.create(ws, Drawing, "Plan")
    assert isinstance(made, Applied)
    head = (await ws.get(Drawing, made.artifact_id)).data
    assert (head.name, head.content.media_type) == ("Plan.dwg", DWG)


@pytest.mark.parametrize(
    ("file_type", "named"),
    [(Drawing, None), (WordDocument, DXF)],
    ids=["none-named-of-several", "another-named"],
)
async def test_a_blank_file_of_no_format_of_the_type_is_refused(
    file_type: type[NativeFile], named: str | None
) -> None:
    ws = await workspace(ALICE)
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming(named))
    with pytest.raises(ValidationFailed, match="another format"):
        await files.create(ws, file_type, "Plan")
    assert await ws.artifacts(NativeFile) == []


async def test_a_blank_file_past_its_formats_most_is_refused() -> None:
    small = {**FORMATS, DOCX: Format(".docx", lambda _: True, most=10)}
    ws = await workspace()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming(), formats=small)
    with pytest.raises(TooLarge):
        await files.create(ws, WordDocument, "Notes")


async def test_a_blank_file_is_held_to_the_quotas() -> None:
    blobs = InMemoryBlobs(workspace_quota=Quota(files=0))
    ws, files = await workspace(), NativeFiles(blobs, InMemoryCheckouts(), Naming())
    with pytest.raises(OverQuota):
        await files.create(ws, WordDocument, "Notes")
    assert await ws.artifacts(NativeFile) == []


async def test_a_blank_file_takes_one_of_the_tenants_readings() -> None:
    ws = await workspace()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming(), readings=0)
    with pytest.raises(Busy):
        await files.create(ws, WordDocument, "Notes")


async def test_files_are_paced_for_each_person() -> None:
    ws = await workspace()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Naming(), pace=Pace(1))
    await files.create(ws, WordDocument, "One")
    with pytest.raises(Paced) as paced:
        await files.create(ws, WordDocument, "Two")
    assert paced.value.wait is not None
    assert paced.value.wait > 0
    assert "try again in" in str(paced.value)


async def test_a_file_waits_for_no_place_and_counts_against_no_pace() -> None:
    ws, app = await workspace(), Naming()
    gauge, pace = Gauge(1, tenant=1, each=1), Pace(1)
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app, pace=pace, gauge=gauge)
    with gauge.held(("acme", ALICE.participant)) as held:
        assert held
        with pytest.raises(Paced) as paced:
            await files.create(ws, WordDocument, "Notes")
    assert paced.value.wait is None
    assert "shortly" in str(paced.value)
    assert app.made == 0
    assert isinstance(await files.create(ws, WordDocument, "Notes"), Applied)
    assert (files.pace, files.gauge) == (pace, gauge)
