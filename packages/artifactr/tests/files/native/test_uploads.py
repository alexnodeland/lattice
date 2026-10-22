"""A person's upload of a native file, over every store: told by its first bytes, read by the app
before anything is committed, named safely, sent again safely, and read a few at a time.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import get_args

import pytest

from artifactr.core import Applied, InvalidState, Proposed, UserActor, ValidationFailed
from artifactr.files.app import AppFailed, Failure, FakeApp, Inspection
from artifactr.files.blobs import DEFAULT_LIMIT, InMemoryBlobs, Quota, TooLarge, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.craft.project import LIMIT
from artifactr.files.manifest import (
    DOCX,
    FCPROJ,
    AudioSession,
    MotionGraphics,
    NativeFile,
    VideoProject,
    WordDocument,
    Workbook,
)
from artifactr.files.native import FORMATS, Busy, Format, NativeFiles
from artifactr.files.native.formats import PROJECT
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.files.conftest import Stores

ALICE = UserActor(id="alice", name="Alice")
JSON_DOCX = {**FORMATS, DOCX: Format(".docx", lambda head: head.startswith(b"{"))}
"""The formats, with the fake app's files, JSON, as Word documents."""


class Slow(FakeApp):
    """A fake app whose inspections wait to be let through."""

    def __init__(self) -> None:
        super().__init__()
        self.inspecting = asyncio.Event()
        self.through = asyncio.Event()

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        self.inspecting.set()
        await self.through.wait()
        return await super().inspect(source, deadline=deadline)


async def workspace() -> Workspace:
    return await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)


def native(stores: Stores, app: FakeApp, *, readings: int | None = None) -> NativeFiles:
    return NativeFiles(stores.blobs, stores.checkouts, app, formats=JSON_DOCX, readings=readings)


async def committed(ws: Workspace) -> list[str]:
    return [artifact.id for artifact in await ws.artifacts(NativeFile)]


async def test_an_upload_is_of_the_format_its_first_bytes_are(stores: Stores) -> None:
    ws, files = await workspace(), native(stores, FakeApp())
    data = once(FakeApp.file("Terms"))
    uploaded = await files.upload(ws, WordDocument, "../x/re\x07port.v2", data, artifact_id="a1")
    assert isinstance(uploaded, Applied)
    head = (await ws.get(WordDocument, "a1")).data
    assert (head.name, head.content.media_type) == ("re_port.v2.docx", DOCX)
    assert head.provenance.source == "upload"


async def test_bytes_of_no_format_of_the_type_are_refused_and_never_stored(
    stores: Stores,
) -> None:
    ws, files = await workspace(), native(stores, FakeApp())
    for junk in (b"MZ\x90\x00 not a document", b""):
        with pytest.raises(AppFailed) as raised:
            await files.upload(ws, WordDocument, "w.docx", once(junk), artifact_id="a1")
        assert raised.value.failure == "refused"
    assert await committed(ws) == []
    with pytest.raises(AppFailed, match="refused"):
        await files.upload(ws, Workbook, "w.xlsx", once(FakeApp.file("x")), artifact_id="a1")


@pytest.mark.parametrize("failure", get_args(Failure))
async def test_a_file_the_app_cant_read_commits_nothing(stores: Stores, failure: Failure) -> None:
    ws, files = await workspace(), native(stores, FakeApp(fails=failure))
    with pytest.raises(AppFailed):
        await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file("x")), artifact_id="a1")
    assert await committed(ws) == []


async def test_a_file_the_app_reads_as_another_format_is_refused(stores: Stores) -> None:
    class Other(FakeApp):
        async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
            read = await super().inspect(source, deadline=deadline)
            return read.model_copy(update={"media_type": "text/x-<b>shaped</b>"})

    ws, files = await workspace(), native(stores, Other())
    with pytest.raises(ValidationFailed) as raised:
        await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file("x")))
    assert "shaped" not in str(raised.value.payload()), "the worker's text is never told"
    assert await committed(ws) == []


async def test_a_zip_the_app_names_no_format_of_is_refused(stores: Stores) -> None:
    class Silent(FakeApp):
        async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
            return Inspection(fingerprint="0" * 64)

    files = NativeFiles(stores.blobs, stores.checkouts, Silent())
    ws = await workspace()
    zipped = once(b"PK\x03\x04" + b"\x00" * 64)
    with pytest.raises(ValidationFailed, match="another format"):
        await files.upload(ws, WordDocument, "w.docx", zipped)
    assert await committed(ws) == []


async def test_a_refused_upload_holds_nothing_against_a_quota() -> None:
    blobs = InMemoryBlobs(workspace_quota=Quota(bytes=10_000, files=1))
    files = NativeFiles(blobs, InMemoryCheckouts(), FakeApp(fails="refused"), formats=JSON_DOCX)
    ws = await workspace()
    for i in range(3):
        with pytest.raises(AppFailed):
            await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file(str(i))))
    files = NativeFiles(blobs, InMemoryCheckouts(), FakeApp(), formats=JSON_DOCX)
    uploaded = await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file("ok")))
    assert isinstance(uploaded, Applied), "the quota's one file was never taken"


async def test_an_upload_sent_again_makes_nothing_twice(stores: Stores) -> None:
    ws, files = await workspace(), native(stores, FakeApp())
    file = FakeApp.file("Terms")
    first = await files.upload(ws, WordDocument, "w.docx", once(file), artifact_id="a1")
    again = await files.upload(ws, WordDocument, "w.docx", once(file), artifact_id="a1")
    assert isinstance(first, Applied)
    assert again is None
    assert (await ws.get(WordDocument, "a1")).version == 1
    with pytest.raises(InvalidState, match="a1 already exists"):
        await files.upload(
            ws, WordDocument, "w.docx", once(FakeApp.file("Other")), artifact_id="a1"
        )


async def test_a_tenant_has_only_so_many_files_read_at_once(stores: Stores) -> None:
    app = Slow()
    ws, files = await workspace(), native(stores, app, readings=1)

    async def upload(artifact_id: str) -> Applied | Proposed | None:
        data = once(FakeApp.file(artifact_id))
        return await files.upload(ws, WordDocument, "w.docx", data, artifact_id=artifact_id)

    assert files.readings == 1
    first = asyncio.create_task(upload("a1"))
    await app.inspecting.wait()
    with pytest.raises(Busy, match="1 of the tenant's files are being read") as raised:
        await upload("a2")
    assert raised.value.limit == 1
    other = await Workspaces(InMemoryStorage()).open("globex", "w1", actor=ALICE)
    second = asyncio.create_task(
        files.upload(other, WordDocument, "w.docx", once(FakeApp.file("b")), artifact_id="b1")
    )
    await asyncio.sleep(0)
    app.through.set()
    assert isinstance(await first, Applied)
    assert isinstance(await second, Applied), "another tenant's reading isn't held up"
    assert isinstance(await upload("a2"), Applied), "the reading was given back"


def test_a_type_is_uploaded_by_its_formats_extensions(stores: Stores) -> None:
    files = NativeFiles(stores.blobs, stores.checkouts, {WordDocument: FakeApp()})
    assert files.extensions(WordDocument) == [".docx"]
    assert files.extensions(Workbook) == [], "no app reads it"


class Names(FakeApp):
    """A fake app that reads every file as one format, as a crafting app names its own."""

    def __init__(self, media_type: str) -> None:
        super().__init__()
        self.media_type = media_type

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        return Inspection(fingerprint="0" * 64, media_type=self.media_type)


@pytest.mark.parametrize("file_type", [MotionGraphics, AudioSession])
async def test_a_project_of_one_crafting_app_is_refused_as_anothers(
    stores: Stores, file_type: type[NativeFile]
) -> None:
    files = NativeFiles(stores.blobs, stores.checkouts, Names(FCPROJ))
    ws = await workspace()
    with pytest.raises(ValidationFailed, match="another format"):
        await files.upload(ws, file_type, "cut.fcproj", once(b'{"tracks": []}'))
    uploaded = await files.upload(ws, VideoProject, "cut.fcproj", once(b'{"tracks": []}'))
    assert isinstance(uploaded, Applied)


async def test_a_bare_object_no_app_names_is_refused(stores: Stores) -> None:
    class Silent(FakeApp):
        async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
            return Inspection(fingerprint="0" * 64)

    files = NativeFiles(stores.blobs, stores.checkouts, Silent())
    with pytest.raises(ValidationFailed, match="another format"):
        await files.upload(await workspace(), VideoProject, "x.fcproj", once(b"{}"))


async def test_a_refused_check_in_holds_nothing_against_a_quota() -> None:
    blobs = InMemoryBlobs(workspace_quota=Quota(bytes=4_000))
    app = FakeApp()
    files = NativeFiles(blobs, InMemoryCheckouts(), app, formats=JSON_DOCX)
    ws = await workspace()
    await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file("x")), artifact_id="a1")
    checkout = await files.check_out(ws, "a1")
    app.fails = "refused"
    for _ in range(5):
        with pytest.raises(AppFailed):
            await files.check_in(ws, checkout.id, once(FakeApp.file("y" * 800)))
    app.fails = None
    assert await files.check_in(ws, checkout.id, once(FakeApp.file("z"))), "room was kept"


async def test_a_project_past_what_its_app_reads_is_refused_as_it_streams(stores: Stores) -> None:
    files = NativeFiles(stores.blobs, stores.checkouts, Names(FCPROJ))
    read: list[int] = []

    async def big() -> AsyncIterator[bytes]:
        for i in range(64):
            read.append(i)
            yield b"{" if i == 0 else b" " * (64 << 10)

    with pytest.raises(TooLarge):
        await files.upload(await workspace(), VideoProject, "cut.fcproj", big())
    assert len(read) < 64, "refused before it was all read"


async def test_a_project_of_exactly_its_most_is_taken(stores: Stores) -> None:
    files = NativeFiles(stores.blobs, stores.checkouts, Names(FCPROJ))
    whole = b"{" + b" " * (PROJECT - 2) + b"}"
    uploaded = await files.upload(await workspace(), VideoProject, "cut.fcproj", once(whole))
    assert isinstance(uploaded, Applied)


async def test_a_format_with_no_most_of_its_own_takes_the_stores() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Names(DOCX))
    zipped = once(b"PK\x03\x04" + b"\x00" * (PROJECT + 1))
    assert await files.upload(await workspace(), WordDocument, "w.docx", zipped)
    assert files.most(WordDocument) == DEFAULT_LIMIT
    assert files.most(VideoProject) == PROJECT


async def test_a_check_in_past_its_formats_most_is_refused_as_it_streams() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Names(FCPROJ))
    ws = await workspace()
    await files.upload(ws, VideoProject, "cut.fcproj", once(b"{}"), artifact_id="a1")
    checkout = await files.check_out(ws, "a1")
    with pytest.raises(TooLarge):
        await files.check_in(ws, checkout.id, once(b"{" + b" " * PROJECT + b"}"))


def test_a_projects_most_is_what_its_adapter_reads() -> None:
    assert PROJECT == LIMIT
