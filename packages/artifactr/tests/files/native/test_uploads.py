"""A person's upload of a native file, over every store: told by its first bytes, read by the app
before anything is committed, named safely, sent again safely, and read a few at a time.
"""

import asyncio
from typing import get_args

import pytest

from artifactr.core import Applied, InvalidState, Proposed, UserActor, ValidationFailed
from artifactr.files.app import AppFailed, Failure, FakeApp, Inspection
from artifactr.files.blobs import once
from artifactr.files.manifest import DOCX, NativeFile, WordDocument, Workbook
from artifactr.files.native import FORMATS, Busy, Format, NativeFiles
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
            return read.model_copy(update={"media_type": "application/pdf"})

    ws, files = await workspace(), native(stores, Other())
    with pytest.raises(ValidationFailed, match="application/pdf"):
        await files.upload(ws, WordDocument, "w.docx", once(FakeApp.file("x")))
    assert await committed(ws) == []


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
