"""The check-out pilot with WordCraft itself: its browser build served, and a check-out over HTTP.

These run where `ARTIFACTR_TEST_CRAFT` is `wordcraft`, with `ARTIFACTR_TEST_CRAFT_CLI` and
`ARTIFACTR_TEST_CRAFT_WEB` from `scripts/craft wordcraft cli` and `scripts/craft wordcraft web`.
The person's edit in the browser is played by the headless CLI, which shares the browser build's
engine; that the browser build opens and saves under the policy was checked by hand, in Chromium
(lattice RFC-0003, phase 4).
"""

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import HTTPConnection

from artifactr.core import Actor, TenantId, UserActor
from artifactr.files.app import AppCommand
from artifactr.files.blobs import InMemoryBlobs, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.fastapi import editor_app, editor_policy, files_router
from artifactr.files.manifest import DOCX, WordDocument
from artifactr.files.native import NativeFiles
from artifactr.files.wordcraft import Subprocess
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.files.corpus.wordcraft.corpus import CORPUS
from tests.files.wordcraft.test_live import DEADLINE, VERSION

pytestmark = [pytest.mark.craft("wordcraft"), pytest.mark.timeout(120)]
ALICE = UserActor(id="alice")


async def alice(_connection: HTTPConnection) -> tuple[TenantId, Actor]:
    return "acme", ALICE


def test_the_browser_build_is_served_as_released_under_its_policy() -> None:
    build = Path(os.environ["ARTIFACTR_TEST_CRAFT_WEB"])
    client = TestClient(editor_app(build))
    page = client.get("/")
    assert page.content == (build / "index.html").read_bytes()
    assert page.headers["content-security-policy"] == editor_policy(page.text)
    assert "'sha256-" in page.headers["content-security-policy"], "its inline script, by hash"
    [wasm] = build.glob("*_bg.wasm")
    assert client.get(f"/{wasm.name}").headers["content-type"] == "application/wasm"


async def test_a_check_out_edited_in_wordcraft_checks_in_as_a_revision() -> None:
    app = Subprocess(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], version=VERSION)
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app)
    workspaces = Workspaces(InMemoryStorage())
    ws = await workspaces.open("acme", "w1", actor=ALICE)
    source = CORPUS.source("text")
    await files.upload(ws, WordDocument, "t.docx", once(source), media_type=DOCX, artifact_id="a1")
    server = FastAPI()
    server.include_router(files_router(workspaces, files, resolve_actor=alice))
    client = TestClient(server)

    checkout = client.post("/workspaces/w1/files/a1/checkouts").json()
    downloaded = client.get("/workspaces/w1/files/a1/versions/1/content").content
    edit = [AppCommand(name="text.insert", args={"text": "Edited. "})]
    edited = (await app.apply(downloaded, edit, deadline=DEADLINE)).content
    url = f"/workspaces/w1/checkouts/{checkout['id']}/file"
    assert client.put(url, content=edited).json()["outcome"] == "applied"
    assert client.put(url, content=edited).json()["outcome"] == "unchanged", "a retry"
    head = await ws.get(WordDocument, "a1")
    assert (head.version, head.data.provenance.source) == (2, "check_in")
    assert "Edited." in (await files.read(ws, "a1", part="text")).decode()
