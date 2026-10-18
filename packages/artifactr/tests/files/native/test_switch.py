"""The switch: while the app's integration is off in a workspace, no one writes its files there.

Off, nothing is uploaded, checked out, extended, checked in or edited, through `NativeFiles` or,
with artifactr's gate on `key_of`, through any surface that commits; reads go on. A workspace
without an `Integrations` has every app on.
"""

from dataclasses import dataclass
from datetime import timedelta

import pytest

from artifactr.core import EditArtifact, JsonPatch, NotEnabled, UserActor
from artifactr.files.app import AppCommand, FakeApp
from artifactr.files.blobs import InMemoryBlobs, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.manifest import DOCX, WordDocument
from artifactr.files.native import NativeFiles
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces, integration_gate
from tests.files.conftest import Switch

ALICE = UserActor(id="alice", name="Alice")


@dataclass
class World:
    files: NativeFiles
    switch: Switch
    ws: Workspace
    other: Workspace

    def off(self) -> None:
        self.switch.off.add(("acme", "w1", "files:fake"))


@pytest.fixture
async def world() -> World:
    switch = Switch()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp(), integrations=switch)
    workspaces = Workspaces(InMemoryStorage(), gate=integration_gate(switch, files.key_of))
    ws = await workspaces.open("acme", "w1", actor=ALICE)
    other = await workspaces.open("acme", "w2", actor=ALICE)
    for handle in (ws, other):
        upload = once(FakeApp.file("Terms"))
        await files.upload(
            handle, WordDocument, "c.docx", upload, media_type=DOCX, artifact_id="a1"
        )
    return World(files, switch, ws, other)


async def test_it_asks_for_the_apps_key_in_the_workspace(world: World) -> None:
    assert await world.files.enabled(world.ws)
    assert world.switch.asked[-1] == ("acme", "w1", "files:fake")


async def test_off_nothing_is_checked_out_extended_or_checked_in(world: World) -> None:
    checkout = await world.files.check_out(world.ws, "a1")
    world.off()
    assert not await world.files.enabled(world.ws)
    with pytest.raises(NotEnabled, match="files:fake is not available"):
        await world.files.check_out(world.ws, "a1")
    with pytest.raises(NotEnabled):
        await world.files.extend(world.ws, checkout.id)
    with pytest.raises(NotEnabled):
        await world.files.check_in(world.ws, checkout.id, once(FakeApp.file("Terms", "Fees")))
    assert (await world.ws.get(WordDocument, "a1")).version == 1


async def test_off_nothing_is_uploaded_or_edited_before_any_lease(world: World) -> None:
    await world.ws.lease_artifact("a1", holder="someone", ttl=timedelta(hours=1))
    world.off()
    upload = once(FakeApp.file("New"))
    with pytest.raises(NotEnabled):
        await world.files.upload(world.ws, WordDocument, "n.docx", upload, media_type=DOCX)
    add = AppCommand(name="add_paragraph", args={"text": "Fees"})
    with pytest.raises(NotEnabled):
        await world.files.edit(world.ws, "a1", base_version=1, commands=[add], summary="Fees")
    with pytest.raises(NotEnabled):  # not ArtifactBusy: the switch is asked first
        await world.files.check_out(world.ws, "a1")
    assert len(await world.ws.artifacts()) == 1, "no upload was made"


async def test_off_the_gate_refuses_an_edit_on_any_surface(world: World) -> None:
    world.off()
    rename = EditArtifact(
        artifact_id="a1",
        base_version=1,
        patch=JsonPatch(ops=({"op": "replace", "path": "/name", "value": "x.docx"},)),
    )
    with pytest.raises(NotEnabled):
        await world.ws.commit(rename)


async def test_off_its_files_are_still_read(world: World) -> None:
    world.off()
    assert await world.files.read(world.ws, "a1") == FakeApp.file("Terms")
    assert (await world.files.render(world.ws, "a1", 1)).startswith(b"\x89PNG")


async def test_off_in_one_workspace_is_on_in_another(world: World) -> None:
    world.off()
    checkout = await world.files.check_out(world.other, "a1")
    file = once(FakeApp.file("Terms", "Fees"))
    assert await world.files.check_in(world.other, checkout.id, file) is not None


def test_the_key_of_a_native_file_is_the_apps(world: World) -> None:
    assert world.files.key_of("word_document", {}) == "files:fake"
    assert world.files.key_of("note", {}) is None
    assert world.files.key_of("no_such_kind", {}) is None


async def test_without_a_switch_every_workspace_has_it() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    assert await files.enabled(ws)
    assert files.app.integration == "files:fake"
