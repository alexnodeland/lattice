"""Pages rendered for readers: in one of the tenant's readings, kept for the next reader, and
never a starved worker's cause; and an upload to a hidden file's id, refused before it is read.
"""

import asyncio
from datetime import timedelta

import pytest
from pydantic import JsonValue

import artifactr.files.native.files as files_module
from artifactr.core import (
    Actor,
    AgentActor,
    EditArtifact,
    InvalidState,
    JsonPatch,
    NotFound,
    ProposeChange,
    Proposed,
    RespondToProposal,
    TenantId,
    UserActor,
    Visibility,
    WorkspaceId,
)
from artifactr.files.app import AppCommand, AppFailed, FakeApp, Inspection
from artifactr.files.blobs import once
from artifactr.files.manifest import DOCX, Blob, NativeFile, WordDocument
from artifactr.files.native import Busy, ContentUnavailable, NativeFiles
from artifactr.workspace import InMemoryStorage, Scope, Workspace, Workspaces
from tests.files.clock import FakeClock
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
    # Two renders queued ahead of an upload fit in its deadline five times over; twenty would not.
    # Every render reaches the app: none is kept.
    files = native(stores, app, deadline=RENDER * 10, pages=0)
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
    assert any(result is None for result in results), "the tenant's readings held"
    assert app.rendered < len(flood)


class Gated(FakeApp):
    """A fake app whose renders wait to be let through, and say how many are waiting."""

    def __init__(self) -> None:
        super().__init__()
        self.through = asyncio.Event()
        self.waiting = 0
        self._arrived = asyncio.Event()

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        self.waiting += 1
        self._arrived.set()
        await self.through.wait()
        return await super().render(source, page, scale=scale, deadline=deadline)

    async def holding(self, renders: int) -> None:
        """Return once this many renders are in the app, each holding one of its tenant's
        readings: not after a guess at how long their reads before it take."""
        async with asyncio.timeout(10):
            while self.waiting < renders:
                self._arrived.clear()
                await self._arrived.wait()


async def test_a_render_holds_one_of_the_tenants_readings_and_waits_a_while_for_one(
    stores: Stores,
) -> None:
    app = Gated()
    files = native(stores, app, pages=0, deadline=0.5)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    first = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(2)]
    await app.holding(2)
    with pytest.raises(Busy):
        await files.render(ws, "a1", 1)  # after waiting its deadline for a reading
    with pytest.raises(Busy):
        await uploaded(files, ws, "a2")  # an upload is refused at once
    waiting = asyncio.create_task(files.render(ws, "a1", 1))
    app.through.set()  # the waiter has a reading free well within its deadline
    await asyncio.gather(*first)
    assert await waiting, "a page that waited was given the reading let go"


async def test_a_cold_file_of_four_pages_renders_every_page(stores: Stores) -> None:
    app = Serial()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    paragraphs = [str(n) for n in range(12)]
    await files.upload(
        ws, WordDocument, "w.docx", once(FakeApp.file(*paragraphs)), artifact_id="a1"
    )
    pages = await asyncio.gather(*(files.render(ws, "a1", page) for page in range(1, 5)))
    assert len(set(pages)) == 4, "the third and fourth waited for a reading, not refused"


async def test_a_page_kept_for_one_reader_is_never_given_to_one_who_cant_see_it(
    stores: Stores,
) -> None:
    async def hidden(tenant: TenantId, workspace: WorkspaceId, actor: Actor) -> Visibility:
        return Visibility(artifacts=frozenset({"a1"} if actor == BOB else ()))

    app = Serial()
    files = native(stores, app)
    alice = await Workspaces(InMemoryStorage(), hidden=hidden).open("acme", "w1", actor=ALICE)
    await uploaded(files, alice, "a1")
    await files.render(alice, "a1", 1)
    with pytest.raises(NotFound):
        await files.render(alice.as_actor(BOB), "a1", 1)
    assert app.rendered == 1


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
    gated = Gated()
    files_busy = native(stores, gated, pages=0, deadline=0.05)
    await uploaded(files_busy, ws, "a3")
    held = [asyncio.create_task(files_busy.render(ws, "a3", 1)) for _ in range(2)]
    await gated.holding(2)
    paced: list[int] = []
    with pytest.raises(Busy):
        await files_busy.render(ws, "a3", 1, admit=lambda: paced.append(1))
    assert paced == [], "a page refused as busy spends none of its reader's pace"
    gated.through.set()
    await asyncio.gather(*held)

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


async def test_the_least_lately_read_page_is_let_go_first(stores: Stores) -> None:
    app = Serial()
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    probe = native(stores, app)
    await uploaded(probe, ws, "a0")
    size = len(await probe.render(ws, "a0", 1))
    files = native(stores, app, pages=size)  # room for one page
    await uploaded(files, ws, "a1")
    await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file("Other")), artifact_id="a2")
    app.rendered = 0
    await files.render(ws, "a1", 1)
    await files.render(ws, "a2", 1)
    await files.render(ws, "a2", 1)
    await files.render(ws, "a1", 1)
    assert app.rendered == 3, "a1's page was let go for a2's"


async def test_a_proposals_page_is_kept_too(stores: Stores) -> None:
    app = Serial()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    agent = ws.as_actor(AgentActor(thread_id="t1", on_behalf_of=ALICE))
    add = AppCommand(name="add_paragraph", args={"text": "Fees"})
    proposed = await files.edit(agent, "a1", base_version=1, commands=[add], summary="x")
    assert isinstance(proposed, Proposed)
    first = await files.render_proposed(ws, proposed.proposal_id, 1)
    rendered = app.rendered
    assert await files.render_proposed(ws, proposed.proposal_id, 1) == first
    assert app.rendered == rendered


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
    with pytest.raises(InvalidState, match="a1 already exists"):
        await uploaded(files, bob, "a1")
    assert Counting.read == 1, "Bob's file was never read"
    assert [a.id for a in await alice.artifacts(NativeFile)] == ["a1"]


async def waiting(files: NativeFiles, tenant_id: str) -> None:
    """Return once one of the tenant's pages waits for a reading, as the files say."""
    for _ in range(100_000):
        if files.waiting(tenant_id):
            return
        await asyncio.sleep(0)
    raise AssertionError("no page waited")


async def test_past_the_tenants_waiting_a_page_is_refused_at_once(stores: Stores) -> None:
    app = Gated()
    files = NativeFiles(
        stores.blobs, stores.checkouts, app, formats=JSON_DOCX, pages=0, deadline=5.0, waiting=1
    )
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    held = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(2)]
    await app.holding(2)
    waiter = asyncio.create_task(files.render(ws, "a1", 1))
    await waiting(files, "acme")
    started = asyncio.get_running_loop().time()
    with pytest.raises(Busy):
        await files.render(ws, "a1", 1)
    assert asyncio.get_running_loop().time() - started < 1, "refused at once, not after its wait"
    app.through.set()
    await asyncio.gather(*held, waiter)
    assert files.waiting("acme") == 0, "the waiter gave its place back"


async def test_a_page_that_waited_finds_one_rendered_meanwhile(stores: Stores) -> None:
    app = Gated()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    asked = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(3)]
    await app.holding(2)
    app.through.set()
    pages = await asyncio.gather(*asked)
    assert len(set(pages)) == 1
    assert app.waiting == 2, "the third, which waited, found the page kept once it had a reading"


async def test_a_waiters_place_is_given_back_when_it_is_cancelled_or_refused(
    stores: Stores,
) -> None:
    app = Gated()
    files = native(stores, app, pages=0, deadline=0.2)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    held = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(2)]
    await app.holding(2)
    cancelled = asyncio.create_task(files.render(ws, "a1", 1))
    await waiting(files, "acme")
    cancelled.cancel()
    await asyncio.gather(cancelled, return_exceptions=True)
    assert files.waiting("acme") == 0, "cancelled"
    with pytest.raises(Busy):
        await files.render(ws, "a1", 1)
    assert files.waiting("acme") == 0, "refused at its deadline"
    app.through.set()
    await asyncio.gather(*held)


async def test_a_waiters_deadline_is_exact(stores: Stores, monkeypatch: pytest.MonkeyPatch) -> None:
    """The waiter's sleeps, on a clock of the test's: the last is what is left of its deadline."""
    app = Gated()
    files = native(stores, app, pages=0, deadline=0.12)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    held = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(2)]
    await app.holding(2)
    now, slept = [100.0], []
    sleep = asyncio.sleep

    async def asleep(seconds: float) -> None:
        slept.append(round(seconds, 6))
        now[0] += seconds
        await sleep(0)

    monkeypatch.setattr(files_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(files_module.asyncio, "sleep", asleep)
    with pytest.raises(Busy):
        await files.render(ws, "a1", 1)
    monkeypatch.undo()
    assert slept == [0.05, 0.05, 0.02], "refused at its deadline, not a look later"
    app.through.set()
    await asyncio.gather(*held)


async def proposal_naming(files: NativeFiles, ws: Workspace, blob: Blob) -> str:
    """A proposal to the file a1 whose content is the blob given."""
    agent = ws.as_actor(AgentActor(thread_id="t1", on_behalf_of=ALICE))
    op: dict[str, JsonValue] = {
        "op": "replace",
        "path": "/content",
        "value": blob.model_dump(mode="json"),
    }
    change = EditArtifact(artifact_id="a1", base_version=1, patch=JsonPatch(ops=(op,)))
    proposed = await agent.commit(ProposeChange(change=change))
    assert isinstance(proposed, Proposed)
    return proposed.proposal_id


async def test_a_page_kept_for_one_file_is_never_given_for_a_digest_another_names(
    stores: Stores,
) -> None:
    app = Serial()
    files = native(stores, app)
    workspaces = Workspaces(InMemoryStorage())
    globex = await workspaces.open("globex", "w1", actor=BOB)
    await files.upload(
        globex, WordDocument, "g.docx", once(FakeApp.file("Theirs")), artifact_id="g1"
    )
    theirs = (await globex.get(WordDocument, "g1")).data.content
    await files.render(globex, "g1", 1)  # kept, for globex's file
    acme = await workspaces.open("acme", "w1", actor=ALICE)
    await uploaded(files, acme, "a1")
    with pytest.raises(ContentUnavailable):
        await files.render_proposed(acme, await proposal_naming(files, acme, theirs), 1)
    absent = theirs.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ContentUnavailable):
        await files.render_proposed(acme, await proposal_naming(files, acme, absent), 1)


async def test_a_page_kept_for_one_file_is_never_given_for_another_files_digest(
    stores: Stores,
) -> None:
    app = Serial()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    await files.upload(ws, WordDocument, "b.docx", once(FakeApp.file("Other")), artifact_id="a2")
    others = (await ws.get(WordDocument, "a2")).data.content
    await files.render(ws, "a2", 1)  # kept, for a2, in the same workspace
    with pytest.raises(ContentUnavailable):
        await files.render_proposed(ws, await proposal_naming(files, ws, others), 1)


async def test_a_page_whose_bytes_were_collected_is_given_no_more(
    stores: Stores, clock: FakeClock
) -> None:
    app = Serial()
    files = NativeFiles(stores.blobs, stores.checkouts, app, formats=JSON_DOCX, clock=clock)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    one = await stores.blobs.put(Scope("acme", "w1"), "a1", once(FakeApp.file("One")), DOCX)
    first = await proposal_naming(files, ws, one)
    await files.render_proposed(ws, first, 1)  # kept
    await ws.commit(RespondToProposal(proposal_id=first, decision="reject"))
    clock.advance(timedelta(days=2))
    assert await files.collect(ws) == 1, "the rejected proposal's bytes are collected"
    with pytest.raises(ContentUnavailable):
        await files.render_proposed(ws, await proposal_naming(files, ws, one), 1)


async def test_proposals_naming_one_blob_render_it_once_and_others_their_own(
    stores: Stores,
) -> None:
    app = Serial()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    scope = Scope("acme", "w1")
    one = await stores.blobs.put(scope, "a1", once(FakeApp.file("One")), DOCX)
    two = await stores.blobs.put(scope, "a1", once(FakeApp.file("Two")), DOCX)
    first, again = [await proposal_naming(files, ws, one) for _ in range(2)]
    other = await proposal_naming(files, ws, two)
    page = await files.render_proposed(ws, first, 1)
    assert await files.render_proposed(ws, again, 1) == page
    assert app.rendered == 1, "the same blob, under two proposals, rendered once"
    assert await files.render_proposed(ws, other, 1) != page
    assert app.rendered == 2, "another blob isn't the first's page"


async def test_a_proposal_that_changes_no_content_has_no_page(stores: Stores) -> None:
    app = Gated()
    files = native(stores, app)
    ws = await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)
    await uploaded(files, ws, "a1")
    agent = ws.as_actor(AgentActor(thread_id="t1", on_behalf_of=ALICE))
    op: dict[str, JsonValue] = {"op": "replace", "path": "/name", "value": "renamed.docx"}
    change = EditArtifact(artifact_id="a1", base_version=1, patch=JsonPatch(ops=(op,)))
    proposed = await agent.commit(ProposeChange(change=change))
    assert isinstance(proposed, Proposed)
    paced: list[int] = []
    held = [asyncio.create_task(files.render(ws, "a1", 1)) for _ in range(2)]
    await app.holding(2)  # both readings taken: one asked for now would wait, then be refused
    with pytest.raises(ContentUnavailable):
        await files.render_proposed(ws, proposed.proposal_id, 1, admit=lambda: paced.append(1))
    assert (paced, files.waiting("acme")) == ([], 0), "refused before a reading or the pace"
    app.through.set()
    await asyncio.gather(*held)
