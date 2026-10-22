"""The check-out routes, over HTTP, with the fake app and header-based auth.

A person checks a file out, downloads it, checks the edit in, fresh, unchanged, stale or too
large; pages are rendered; and in a workspace where the app is off, nothing is checked out.
"""

import io
import json
import runpy
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import HTTPConnection

from artifactr.core import (
    Actor,
    AgentActor,
    Proposed,
    TenantId,
    UserActor,
    Visibility,
    WorkspaceId,
)
from artifactr.fastapi import Unauthorized
from artifactr.files.app import AppCommand, FakeApp
from artifactr.files.blobs import InMemoryBlobs, once
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.fastapi import files_router
from artifactr.files.fastapi.openapi import openapi_app, openapi_document
from artifactr.files.manifest import DOCX, WordDocument
from artifactr.files.native import NativeFiles
from artifactr.workspace import Access, InMemoryStorage, Workspace, Workspaces, integration_gate
from tests.files.clock import FakeClock
from tests.files.conftest import Switch

ALICE = UserActor(id="alice")
LIMIT = 4096
"""The router's limit, half its store's, so a refusal from either is told apart."""
DOCUMENT = Path(__file__).parents[3] / "schemas" / "artifactr-files.openapi.json"
FILE = "/workspaces/w1/files/a1"


async def authorize(
    tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
) -> bool:
    """Refuse the workspace `secret`."""
    return workspace_id != "secret"


async def hidden(tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor) -> Visibility:
    """Hide `a1` from Eve."""
    return Visibility(artifacts=frozenset({"a1"} if actor.participant == "user:eve" else ()))


async def resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    if connection.headers.get("x-token") == "bad":
        raise Unauthorized
    return "acme", UserActor(id=connection.headers.get("x-user", "alice"))


@dataclass
class World:
    client: TestClient
    switch: Switch
    app: FakeApp
    clock: FakeClock
    ws: Workspace
    files: NativeFiles

    def as_(self, user: str) -> dict[str, str]:
        return {"x-user": user}

    def check_out(self, user: str = "alice") -> dict[str, Any]:
        response = self.client.post(f"{FILE}/checkouts", headers=self.as_(user))
        assert response.status_code == 201, response.text
        return response.json()

    def check_in(self, checkout: dict[str, Any], body: bytes, user: str = "alice") -> Any:
        url = f"/workspaces/w1/checkouts/{checkout['id']}/file"
        return self.client.put(url, content=body, headers=self.as_(user))


@pytest.fixture
async def world() -> World:
    switch, app, clock = Switch(), FakeApp(), FakeClock()
    blobs = InMemoryBlobs(limit=2 * LIMIT)
    files = NativeFiles(blobs, InMemoryCheckouts(), app, integrations=switch)
    workspaces = Workspaces(
        InMemoryStorage(clock=clock),
        authorize=authorize,
        hidden=hidden,
        gate=integration_gate(switch, files.key_of),
    )
    ws = await workspaces.open("acme", "w1", actor=ALICE)
    upload = once(FakeApp.file("Terms"))
    await files.upload(ws, WordDocument, "c ø.docx", upload, media_type=DOCX, artifact_id="a1")
    server = FastAPI()
    server.include_router(files_router(workspaces, files, resolve_actor=resolve_actor, limit=LIMIT))
    return World(TestClient(server), switch, app, clock, ws, files)


def test_a_file_says_who_has_it_and_how_it_is_edited(world: World) -> None:
    status = world.client.get(FILE).json()
    assert status == {
        "artifact_id": "a1",
        "version": 1,
        "name": "c ø.docx",
        "media_type": DOCX,
        "size": len(FakeApp.file("Terms")),
        "outline": "Terms",
        "pages": 1,
        "lease": None,
        "talk": "save",
        "enabled": True,
        "limit": LIMIT,
    }
    checkout = world.check_out()
    lease = world.client.get(FILE).json()["lease"]
    assert lease["checked_out_by"] == "user:alice"
    assert lease["expires_at"] == checkout["expires_at"]
    assert lease["checkout_id"] == checkout["id"], "to its holder"
    assert world.client.get(FILE, headers=world.as_("bob")).json()["lease"]["checkout_id"] is None


def test_a_check_out_then_a_check_in_is_a_revision(world: World) -> None:
    checkout = world.check_out()
    download = world.client.get(f"{FILE}/versions/1/content")
    assert download.content == FakeApp.file("Terms")
    assert download.headers["content-type"] == DOCX
    assert download.headers["content-disposition"] == (
        "attachment; filename=\"c ?.docx\"; filename*=UTF-8''c%20%C3%B8.docx"
    )
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-security-policy"] == "sandbox"
    assert download.headers["cache-control"] == "private, no-store"
    edited = FakeApp.file("Terms", "Fees")
    answered = world.check_in(checkout, edited)
    assert answered.json() == {"outcome": "applied", "version": 2, "proposal_id": None}
    assert world.check_in(checkout, edited).json()["outcome"] == "unchanged", "a retry"
    assert world.client.get(f"{FILE}/versions/2/content").content == edited
    assert world.client.get(FILE).json()["lease"] is None


def test_someone_elses_check_out_is_refused(world: World) -> None:
    checkout = world.check_out()
    busy = world.client.post(f"{FILE}/checkouts", headers=world.as_("bob"))
    assert busy.status_code == 409
    forbidden = world.check_in(checkout, FakeApp.file("x"), user="bob")
    assert forbidden.status_code == 403


def test_a_check_in_after_someone_elses_is_a_proposal(world: World) -> None:
    alices = world.check_out()
    world.clock.advance(timedelta(hours=9))  # Alice's check-out lapses, and Bob takes the file
    bobs = world.check_out("bob")
    assert world.check_in(bobs, FakeApp.file("Terms", "Bob's"), user="bob").status_code == 200
    stale = world.check_in(alices, FakeApp.file("Terms", "Alice's")).json()
    assert stale["outcome"] == "proposed"
    assert stale["proposal_id"]


def test_extending_a_check_out_renews_its_lease(world: World) -> None:
    checkout = world.check_out()
    world.clock.advance(timedelta(hours=1))
    extended = world.client.post(f"/workspaces/w1/checkouts/{checkout['id']}/extension")
    assert extended.status_code == 200
    assert extended.json()["expires_at"] == (
        world.clock.now + timedelta(hours=8)
    ).isoformat().replace("+00:00", "Z")


def test_a_check_in_past_the_limit_is_refused_before_it_is_read(world: World) -> None:
    checkout = world.check_out()
    declared = world.check_in(checkout, b"x" * (LIMIT + 1))
    assert declared.status_code == 413
    assert declared.json()["detail"] == f"the file is larger than {LIMIT} bytes", "the router's"

    def chunks() -> Any:  # sent chunked, with no Content-Length: the store refuses it
        yield b"x" * (2 * LIMIT)
        yield b"x"

    url = f"/workspaces/w1/checkouts/{checkout['id']}/file"
    streamed = world.client.put(url, content=chunks())
    assert streamed.status_code == 413
    assert streamed.json()["detail"] == f"the file is larger than {2 * LIMIT} bytes", "the store's"


def test_a_versions_words_are_its_text_as_the_app_read_them(world: World) -> None:
    checkout = world.check_out()
    world.check_in(checkout, FakeApp.file("Terms", "Fees"))
    first = world.client.get(f"{FILE}/versions/1/text")
    assert first.text == "Terms"
    assert first.headers["content-type"] == "text/plain; charset=utf-8"
    assert first.headers["content-security-policy"] == "sandbox"
    assert world.client.get(f"{FILE}/versions/2/text").text == "Terms\n\nFees"
    assert world.client.get(f"{FILE}/versions/3/text").status_code == 404


async def test_a_version_with_no_words_has_none_to_give(world: World) -> None:
    head = await world.ws.get(WordDocument, "a1")
    await world.ws.commit(head.edit(lambda data: setattr(data, "text", None)))
    refused = world.client.get(f"{FILE}/versions/2/text")
    assert (refused.status_code, refused.json()["detail"]["type"]) == (409, "invalid_state")


async def test_a_proposal_is_read_and_rendered_beside_the_head(world: World) -> None:
    agent = world.ws.as_actor(AgentActor(thread_id="t1", on_behalf_of=ALICE))
    proposed = await world.files.edit(
        agent,
        "a1",
        base_version=1,
        commands=[AppCommand(name="add_paragraph", args={"text": "Fees"})],
        summary="x",
    )
    assert isinstance(proposed, Proposed)
    at = f"/workspaces/w1/proposals/{proposed.proposal_id}"
    text = world.client.get(f"{at}/text")
    assert (text.text, text.headers["content-security-policy"]) == ("Terms\n\nFees", "sandbox")
    page = world.client.get(f"{at}/pages/1")
    assert (page.status_code, page.headers["content-type"]) == (200, "image/png")
    assert world.client.get(f"{at}/pages/2").status_code == 422
    for read in ("text", "pages/1"):
        assert world.client.get(f"{at}/{read}", headers=world.as_("eve")).status_code == 404
        assert world.client.get(f"/workspaces/w1/proposals/zz/{read}").status_code == 404


def test_a_page_is_a_png_and_one_past_the_end_is_refused(world: World) -> None:
    world.app.fails = "timeout"
    assert world.client.get(f"{FILE}/versions/1/pages/1").status_code == 503
    world.app.fails = None
    page = world.client.get(f"{FILE}/versions/1/pages/1")
    assert (page.status_code, page.headers["content-type"]) == (200, "image/png")
    assert page.content.startswith(b"\x89PNG")
    missing = world.client.get(f"{FILE}/versions/1/pages/9")
    assert missing.status_code == 422
    assert missing.json()["detail"]["failure"] == "refused"


def test_a_page_is_kept_by_its_reader_and_told_by_its_tag(world: World) -> None:
    page = world.client.get(f"{FILE}/versions/1/pages/1")
    assert page.headers["cache-control"] == "private, max-age=86400"
    tag = page.headers["etag"]
    kept = world.client.get(f"{FILE}/versions/1/pages/1", headers={"if-none-match": tag})
    assert (kept.status_code, kept.content, kept.headers["etag"]) == (304, b"", tag)
    other = world.client.get(f"{FILE}/versions/1/pages/1", headers={"if-none-match": '"x"'})
    assert other.status_code == 200


async def test_each_persons_pages_that_reach_the_app_are_paced() -> None:
    app = FakeApp()
    files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), app, pages=0)
    workspaces = Workspaces(InMemoryStorage(), authorize=authorize, hidden=hidden)
    ws = await workspaces.open("acme", "w1", actor=ALICE)
    await files.upload(
        ws, WordDocument, "c.docx", once(FakeApp.file("x")), media_type=DOCX, artifact_id="a1"
    )
    server = FastAPI()
    server.include_router(
        files_router(workspaces, files, resolve_actor=resolve_actor, renders_per_minute=2)
    )
    client = TestClient(server)
    page = f"{FILE}/versions/1/pages/1"
    assert [client.get(page).status_code for _ in range(2)] == [200, 200]
    paced = client.get(page)
    assert (paced.status_code, paced.json()["detail"]["type"]) == (429, "rate_limited")
    assert client.get(page, headers={"x-user": "bob"}).status_code == 200, "another's own pace"


def test_an_app_that_cant_read_a_check_in_says_why(world: World) -> None:
    checkout = world.check_out()
    refused = world.check_in(checkout, b"not the app's")
    assert refused.status_code == 422
    assert refused.json()["detail"]["type"] == "app_failed"


def test_switched_off_nothing_is_checked_out_but_the_file_is_read(world: World) -> None:
    world.switch.off.add(("acme", "w1", "files:fake"))
    refused = world.client.post(f"{FILE}/checkouts")
    assert refused.status_code == 409
    assert refused.json()["detail"]["type"] == "not_enabled"
    assert world.client.get(FILE).json()["enabled"] is False
    assert world.client.get(f"{FILE}/versions/1/content").status_code == 200


def test_a_missing_version_or_file_is_not_found(world: World) -> None:
    assert world.client.get(f"{FILE}/versions/7/content").status_code == 404
    assert world.client.get("/workspaces/w1/files/zz").status_code == 404


async def test_an_agents_edit_holds_the_file_for_no_one_named(world: World) -> None:
    await world.ws.lease_artifact("a1", holder="edit:someone", ttl=timedelta(seconds=45))
    lease = world.client.get(FILE).json()["lease"]
    assert (lease["checked_out_by"], lease["checkout_id"]) == (None, None)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", FILE),
        ("post", f"{FILE}/checkouts"),
        ("get", f"{FILE}/versions/1/content"),
        ("get", f"{FILE}/versions/1/text"),
        ("get", f"{FILE}/versions/1/pages/1"),
    ],
)
def test_a_hidden_file_is_answered_as_a_missing_one(world: World, method: str, path: str) -> None:
    assert world.client.request(method, path, headers=world.as_("eve")).status_code == 404


def test_a_workspace_the_actor_may_not_open_is_forbidden(world: World) -> None:
    assert world.client.get("/workspaces/secret/files/a1").status_code == 403


def test_an_ended_check_out_takes_no_other_file_and_no_extension(world: World) -> None:
    checkout = world.check_out()
    world.check_in(checkout, FakeApp.file("Terms", "Fees"))
    assert world.check_in(checkout, FakeApp.file("Other")).status_code == 409
    extension = world.client.post(f"/workspaces/w1/checkouts/{checkout['id']}/extension")
    assert extension.status_code == 409


def test_no_one_unknown_is_let_in(world: World) -> None:
    assert world.client.get(FILE, headers={"x-token": "bad"}).status_code == 401


def test_the_documents_application_admits_no_one() -> None:
    assert TestClient(openapi_app()).get(FILE).status_code == 401


def test_the_committed_document_is_current() -> None:
    document = json.loads(DOCUMENT.read_text())
    assert document == openapi_document(), "run `moon run artifactr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document() -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        runpy.run_module("artifactr.files.fastapi.openapi", run_name="__main__")
    assert json.loads(output.getvalue()) == openapi_document()
