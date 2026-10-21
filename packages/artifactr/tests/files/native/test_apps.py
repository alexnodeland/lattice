"""Several apps, one for each native type, each behind its own switch; and a check-in in another
format than the one checked out, which is refused and never converted."""

from collections.abc import Sequence
from typing import ClassVar, override

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import HTTPConnection

from artifactr.core import Actor, NotEnabled, NotFound, TenantId, UserActor, ValidationFailed
from artifactr.files.app import AppCommand, Applied, FakeApp, Inspection
from artifactr.files.blobs import InMemoryBlobs, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.fastapi import files_router
from artifactr.files.manifest import DOCX, PDF, XLSX, NativeFile, WordDocument
from artifactr.files.native import FormatChanged, NativeFiles
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.files.conftest import Switch

ALICE = UserActor(id="alice", name="Alice")


class Ledger(NativeFile):
    """A workbook, for an app of its own."""

    formats: ClassVar[frozenset[str]] = frozenset({XLSX})


class Sheets(FakeApp):
    name: str = "sheets"


class Reads(FakeApp):
    """The fake app, reading every file as a format of its choosing."""

    def __init__(self, media_type: str) -> None:
        super().__init__()
        self.media_type = media_type

    @override
    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        read = await super().inspect(source, deadline=deadline)
        return read.model_copy(update={"media_type": self.media_type})

    @override
    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        applied = await super().apply(source, commands, deadline=deadline)
        inspection = applied.inspection.model_copy(update={"media_type": self.media_type})
        return Applied(content=applied.content, inspection=inspection)


async def opened() -> Workspace:
    return await Workspaces(InMemoryStorage()).open("acme", "w1", actor=ALICE)


async def test_each_type_is_read_and_edited_by_its_own_app() -> None:
    words, sheets = FakeApp(), Sheets(integration="files:sheets")
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), {NativeFile: words, Ledger: sheets})
    ws = await opened()
    await files.upload(
        ws, WordDocument, "a.docx", once(FakeApp.file("A")), media_type=DOCX, artifact_id="a"
    )
    await files.upload(
        ws, Ledger, "b.xlsx", once(FakeApp.file("B")), media_type=XLSX, artifact_id="b"
    )
    edit = [AppCommand(name="add_paragraph", args={"text": "More"})]
    for artifact_id in ("a", "b"):
        await files.edit(ws, artifact_id, base_version=1, commands=edit, summary="More")
    made = {a: (await ws.get(NativeFile, a)).data.provenance.app for a in ("a", "b")}
    assert made == {"a": "fake", "b": "sheets"}
    assert files.app_of(WordDocument) is words
    assert files.app_of(Ledger) is sheets
    assert files.key_of("ledger", {}) == "files:sheets"
    assert files.key_of("word_document", {}) == "files:fake"


async def test_each_app_is_switched_on_its_own() -> None:
    switch = Switch()
    switch.off.add(("acme", "w1", "files:sheets"))
    apps = {WordDocument: FakeApp(), Ledger: Sheets(integration="files:sheets")}
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), apps, integrations=switch)
    ws = await opened()
    assert await files.enabled(ws), "one app is on"
    assert await files.enabled(ws, WordDocument)
    assert not await files.enabled(ws, Ledger)
    with pytest.raises(NotEnabled, match="files:sheets"):
        await files.upload(ws, Ledger, "b.xlsx", once(FakeApp.file("B")), media_type=XLSX)
    await files.upload(ws, WordDocument, "a.docx", once(FakeApp.file("A")), media_type=DOCX)
    switch.off.add(("acme", "w1", "files:fake"))
    assert not await files.enabled(ws), "every app is off"


async def test_a_type_no_app_reads_is_refused_and_governed_by_no_switch() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), {WordDocument: FakeApp()})
    ws = await opened()
    with pytest.raises(ValidationFailed, match="no app reads a ledger"):
        await files.upload(ws, Ledger, "b.xlsx", once(FakeApp.file("B")), media_type=XLSX)
    assert not await files.enabled(ws, Ledger)
    assert files.key_of("ledger", {}) is None
    assert files.key_of("note", {}) is None, "not a native file"


def test_native_files_need_an_app() -> None:
    with pytest.raises(ValueError, match="need an app"):
        NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), {})


async def test_an_upload_the_app_reads_as_another_format_is_refused() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Reads(PDF))
    ws = await opened()
    with pytest.raises(ValidationFailed, match="another format than its kind's"):
        await files.upload(ws, WordDocument, "a.docx", once(FakeApp.file("A")), media_type=DOCX)


@pytest.mark.parametrize(("declared", "read"), [(PDF, None), (None, PDF)])
async def test_a_check_in_in_another_format_is_refused_and_never_converted(
    declared: str | None, read: str | None
) -> None:
    app = FakeApp() if read is None else Reads(read)
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app)
    ws = await opened()
    upload = once(FakeApp.file("A"))
    if read is None:
        await files.upload(ws, WordDocument, "a.docx", upload, media_type=DOCX, artifact_id="a")
    else:
        await NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp()).upload(
            ws, WordDocument, "a.docx", upload, media_type=DOCX, artifact_id="a"
        )
    checkout = await files.check_out(ws, "a")
    with pytest.raises(FormatChanged) as refused:
        await files.check_in(ws, checkout.id, once(FakeApp.file("B")), media_type=declared)
    assert refused.value.details() == {"checked_out": DOCX, "checked_in": PDF}
    assert "upload it as a new file" in str(refused.value)
    assert (await ws.get(NativeFile, "a")).version == 1


async def test_a_check_in_in_its_own_format_goes_in() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), Reads(DOCX))
    ws = await opened()
    await files.upload(
        ws, WordDocument, "a.docx", once(FakeApp.file("A")), media_type=DOCX, artifact_id="a"
    )
    checkout = await files.check_out(ws, "a")
    applied = await files.check_in(ws, checkout.id, once(FakeApp.file("B")), media_type=DOCX)
    assert applied is not None


async def alice(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    return "acme", ALICE


@pytest.mark.parametrize(
    ("content_type", "status"),
    [
        ("application/pdf", 409),
        ("application/octet-stream", 200),
        ("text/plain", 200),
        (f"{DOCX}; charset=binary", 200),
    ],
)
async def test_the_router_takes_the_check_ins_format_from_its_content_type(
    content_type: str, status: int
) -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    workspaces = Workspaces(InMemoryStorage())
    ws = await workspaces.open("acme", "w1", actor=ALICE)
    await files.upload(
        ws, WordDocument, "a.docx", once(FakeApp.file("A")), media_type=DOCX, artifact_id="a"
    )
    server = FastAPI()
    server.include_router(files_router(workspaces, files, resolve_actor=alice))
    client = TestClient(server)
    checkout = client.post("/workspaces/w1/files/a/checkouts").json()
    put = client.put(
        f"/workspaces/w1/checkouts/{checkout['id']}/file",
        content=FakeApp.file("B"),
        headers={"Content-Type": content_type},
    )
    assert put.status_code == status, put.text
    if status == 409:
        assert put.json()["detail"]["checked_in"] == "application/pdf"


async def test_a_check_out_of_a_file_whose_app_is_off_is_refused_before_any_lease() -> None:
    switch = Switch()
    apps = {WordDocument: FakeApp(), Ledger: Sheets(integration="files:sheets")}
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), apps, integrations=switch)
    ws = await opened()
    upload = once(FakeApp.file("B"))
    await files.upload(ws, Ledger, "b.xlsx", upload, media_type=XLSX, artifact_id="b")
    switch.off.add(("acme", "w1", "files:sheets"))
    with pytest.raises(NotEnabled, match="files:sheets"):
        await files.check_out(ws, "b")
    assert await ws.artifact_lease("b") is None
    with pytest.raises(NotFound):
        await files.check_out(ws, "missing")  # a file is found before its app is asked


async def test_after_a_check_in_in_another_format_the_right_one_goes_in() -> None:
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
    ws = await opened()
    upload = once(FakeApp.file("A"))
    await files.upload(ws, WordDocument, "a.docx", upload, media_type=DOCX, artifact_id="a")
    checkout = await files.check_out(ws, "a")
    with pytest.raises(FormatChanged):
        await files.check_in(ws, checkout.id, once(FakeApp.file("B")), media_type=PDF)
    applied = await files.check_in(ws, checkout.id, once(FakeApp.file("B")), media_type=DOCX)
    assert applied is not None, "the check-out stayed open"
