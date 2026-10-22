"""Pages rendered for readers: in one of the tenant's readings, kept for the next reader, and
never a starved worker's cause; and an upload to a hidden file's id, refused before it is read.
"""

import asyncio

import pytest

from artifactr.core import Actor, NotFound, TenantId, UserActor, Visibility, WorkspaceId
from artifactr.files.app import AppFailed, FakeApp, Inspection
from artifactr.files.blobs import once
from artifactr.files.manifest import NativeFile, WordDocument
from artifactr.files.native import Busy, NativeFiles
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.files.conftest import Stores
from tests.files.native.test_uploads import JSON_DOCX

ALICE = UserActor(id="alice", name="Alice")
BOB = UserActor(id="bob", name="Bob")
RENDER = 0.1
"""How long the serial app takes to render a page."""


class Serial(FakeApp):
    """A fake app that does one call at a time, as a worker does, failing a call that waits past
    its deadline, and counting what it renders.
    """

    def __init__(self) -> None:
        super().__init__()
        self.turn = asyncio.Lock()
        self.rendered = 0

    async def _taken(self, deadline: float) -> None:
        try:
            await asyncio.wait_for(self.turn.acquire(), deadline)
        except TimeoutError:
            raise AppFailed("timeout", "the worker was busy") from None

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        await self._taken(deadline)
        try:
            self.rendered += 1
            await asyncio.sleep(RENDER)
            return await super().render(source, page, scale=scale, deadline=deadline)
        finally:
            self.turn.release()

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        await self._taken(deadline)
        try:
            return await super().inspect(source, deadline=deadline)
        finally:
            self.turn.release()


def native(
    stores: Stores, app: FakeApp, *, deadline: float = 30.0, pages: int = 64 << 20
) -> NativeFiles:
    return NativeFiles(
        stores.blobs, stores.checkouts, app, formats=JSON_DOCX, deadline=deadline, pages=pages
    )


async def uploaded(files: NativeFiles, ws: Workspace, artifact_id: str) -> None:
    data = once(FakeApp.file("Terms"))
    await files.upload(ws, WordDocument, "w.docx", data, artifact_id=artifact_id)


async def test_a_flood_of_one_tenants_renders_never_times_another_tenants_upload_out(
    stores: Stores,
) -> None:
    app = Serial()
    # Two renders queued ahead of an upload fit in its deadline; twenty would not.
    # Every render reaches the app: none is kept.
    files = native(stores, app, deadline=RENDER * 3.5, pages=0)
    workspaces = Workspaces(InMemoryStorage())
    acme = await workspaces.open("acme", "w1", actor=ALICE)
    globex = await workspaces.open("globex", "w1", actor=BOB)
    await uploaded(files, acme, "a1")

    async def render() -> bytes | None:
        try:
            return await files.render(acme, "a1", 1)
        except Busy:
            return None

    flood = [asyncio.create_task(render()) for _ in range(20)]
    await asyncio.sleep(0)
    await uploaded(files, globex, "b1")
    results = await asyncio.gather(*flood)
    assert sum(result is None for result in results) >= 18, "the tenant's readings held"
    assert app.rendered <= 2


async def test_a_render_holds_one_of_the_tenants_readings(stores: Stores) -> None:
    app = Serial()
    files = native(stores, app, pages=0)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    first = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(2)]
    await asyncio.sleep(0)
    with pytest.raises(Busy):
        await files.render(ws, "a1", 1)
    await asyncio.gather(*first)
    assert await files.render(ws, "a1", 1), "the readings were given back"


async def test_a_page_rendered_before_is_kept_and_never_paced(stores: Stores) -> None:
    app = Serial()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    admitted: list[int] = []
    first = await files.render(ws, "a1", 1, admit=lambda: admitted.append(1))
    again = await files.render(ws, "a1", 1, version=1, admit=lambda: admitted.append(2))
    assert first == again
    assert (app.rendered, admitted) == (1, [1]), "the second reached neither the app nor the pace"

    class Refused(Exception):
        pass

    def refuse() -> None:
        raise Refused

    with pytest.raises(Refused):
        await files.render(ws, "a1", 2, admit=refuse)
    assert app.rendered == 1, "a page past its reader's pace never reaches the app"


async def test_the_pages_kept_are_held_to_their_bytes(stores: Stores) -> None:
    app = Serial()
    files = native(stores, app, pages=1)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    await files.render(ws, "a1", 1)
    await files.render(ws, "a1", 1)
    assert app.rendered == 2, "a page larger than the whole cache isn't kept"


async def test_an_upload_to_a_hidden_files_id_is_refused_before_it_is_read(
    stores: Stores,
) -> None:
    async def hidden(tenant: TenantId, workspace: WorkspaceId, actor: Actor) -> Visibility:
        return Visibility(artifacts=frozenset({"a1"} if actor == BOB else ()))

    class Counting(FakeApp):
        read = 0

        async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
            Counting.read += 1
            return await super().inspect(source, deadline=deadline)

    files = native(stores, Counting())
    alice = await Workspaces(InMemoryStorage(), hidden=hidden).open("acme", "w1", actor=ALICE)
    await uploaded(files, alice, "a1")
    bob = alice.as_actor(BOB)
    with pytest.raises(NotFound):
        await uploaded(files, bob, "a1")
    assert Counting.read == 1, "Bob's file was never read"
    assert [a.id for a in await alice.artifacts(NativeFile)] == ["a1"]
