"""The images a person puts on a diagram's canvas: uploaded as a PNG or a JPEG of at most 2 MiB,
named by their digest, read back only where the diagram names them, and kept apart by tenant,
workspace and diagram (artifactr ADR-0092)."""

import hashlib
import json
import runpy
import zlib
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent

from artifactr.agent import Runner, Session
from artifactr.core import Actor, TenantId, UserActor, Visibility, WorkspaceId
from artifactr.excalidraw import EXCALIDRAW, EXCALIDRAW_TYPES, excalidraw_checks, excalidraw_key_of
from artifactr.excalidraw.fastapi import MAX_IMAGE, diagrams_router
from artifactr.excalidraw.openapi import openapi_app, openapi_document
from artifactr.fastapi import artifactr_router
from artifactr.files.blobs import InMemoryBlobs, Quota
from artifactr.workspace import Access, InMemoryStorage, Scope, Workspaces, integration_gate
from tests.agent.conftest import Script
from tests.excalidraw.scenes import data, element
from tests.fastapi.conftest import Latch, command, resolve_actor
from tests.ui.toggles import Toggles


def png(width: int = 2, height: int = 2) -> bytes:
    """A PNG, whole, of `width` by `height` pixels of one colour."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4) + kind + body + zlib.crc32(kind + body).to_bytes(4)

    header = width.to_bytes(4) + height.to_bytes(4) + bytes([8, 2, 0, 0, 0])
    rows = (b"\x00" + b"\xcc\x00\x00" * width) * height if width * height <= 64 else b""
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def jpeg(
    width: int = 2, height: int = 2, *, frame_marker: bytes = b"\xc0", exif: bytes = b""
) -> bytes:
    """A JPEG's header, to its frame: a JFIF segment, an EXIF one if given, then its frame."""
    jfif = b"\xff\xe0" + (16).to_bytes(2) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    if exif:
        jfif += b"\xff\xe1" + (len(exif) + 2).to_bytes(2) + exif
    frame = (
        b"\xff"
        + frame_marker
        + (17).to_bytes(2)
        + b"\x08"
        + height.to_bytes(2)
        + width.to_bytes(2)
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + jfif + frame + b"\xff\xd9"


PNG = png()
JPEG = jpeg()


async def authorize(
    tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
) -> bool:
    """Vera only views: she may read, and edit nothing."""
    return not (actor == UserActor(id="vera") and access.action == "artifactr:edit_artifact")


async def hide(tenant: str, workspace: str, actor: Any) -> Visibility:
    """Hal may not see d1: it is hidden from him, as a restricted artifact is."""
    return Visibility(artifacts=frozenset({"d1"}) if actor == UserActor(id="hal") else frozenset())


@pytest.fixture
def toggles() -> Toggles:
    return Toggles()


@pytest.fixture
def blobs() -> InMemoryBlobs:
    return InMemoryBlobs()


@pytest.fixture
def client(toggles: Toggles, blobs: InMemoryBlobs) -> Iterator[TestClient]:
    agent: Agent[Session[Latch], Any] = Agent(Script().model, deps_type=Session[Latch])
    workspaces = Workspaces(
        InMemoryStorage(),
        types=EXCALIDRAW_TYPES,
        checks=excalidraw_checks(),
        gate=integration_gate(toggles, excalidraw_key_of),
        authorize=authorize,
        hidden=hide,
    )
    app = FastAPI()
    app.include_router(
        artifactr_router(workspaces, Runner(agent, app=Latch()), resolve_actor=resolve_actor),
        prefix="/v1",
    )
    app.include_router(
        diagrams_router(
            workspaces,
            blobs,
            resolve_actor=resolve_actor,
            integrations=toggles,
            uploads_per_minute=5,
        ),
        prefix="/v1",
    )
    with TestClient(app) as client:
        yield client


def _as(tenant: str = "tenant", user: str = "alice") -> dict[str, str]:
    return {"x-tenant": tenant, "x-user": user}


def _drawn(
    client: TestClient, workspace: str = "w1", tenant: str = "tenant", diagram: str = "d1"
) -> None:
    made = command(
        f"c1{diagram}",
        type="create_artifact",
        artifact_id=diagram,
        kind="excalidraw_diagram",
        data=data(),
    )
    sent = client.post(f"/v1/workspaces/{workspace}/commands", json=made, headers=_as(tenant))
    assert sent.status_code == 200, sent.text


def _upload(
    client: TestClient,
    body: bytes = PNG,
    media: str = "image/png",
    *,
    workspace: str = "w1",
    diagram: str = "d1",
    **who: str,
) -> Any:
    return client.post(
        f"/v1/workspaces/{workspace}/diagrams/{diagram}/images",
        content=body,
        headers={"Content-Type": media, **_as(**who)},
    )


def _named(
    client: TestClient,
    digest: str,
    size: int,
    media: str,
    version: int = 1,
    diagram: str = "d1",
    tenant: str = "tenant",
) -> None:
    """An edit that names the image, as a canvas's does once it is on the diagram."""
    file = {"sha256": digest, "size": size, "media_type": media}
    picture = element("p1", type="image", fileId=digest).model_dump(mode="json")
    ops = [
        {"op": "add", "path": "/elements/p1", "value": picture},
        {"op": "add", "path": f"/files/{digest}", "value": file},
    ]
    edit = command(
        f"c2{diagram}{tenant}",
        type="edit_artifact",
        artifact_id=diagram,
        base_version=version,
        patch={"kind": "json_patch", "ops": ops},
    )
    sent = client.post("/v1/workspaces/w1/commands", json=edit, headers=_as(tenant))
    assert sent.status_code == 200, sent.text


def test_an_image_is_uploaded_named_by_its_digest_and_read_once_the_diagram_names_it(
    client: TestClient,
) -> None:
    _drawn(client)
    uploaded = _upload(client)
    assert uploaded.status_code == 201
    digest = hashlib.sha256(PNG).hexdigest()
    assert uploaded.json() == {"sha256": digest, "size": len(PNG), "media_type": "image/png"}
    path = f"/v1/workspaces/w1/diagrams/d1/images/{digest}"
    assert client.get(path, headers=_as()).status_code == 404, "unnamed, it isn't served"
    _named(client, digest, len(PNG), "image/png")
    read = client.get(path, headers=_as())
    assert (read.status_code, read.content) == (200, PNG)
    assert read.headers["content-type"] == "image/png"
    assert read.headers["x-content-type-options"] == "nosniff"
    assert read.headers["content-security-policy"] == "sandbox"
    jpeg = _upload(client, JPEG, "image/jpeg")
    assert (jpeg.status_code, jpeg.json()["media_type"]) == (201, "image/jpeg")


@pytest.mark.parametrize(
    ("body", "media", "status", "kind"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", 415, "unsupported"),
        (PNG, "image/gif", 415, "unsupported"),
        (b"<svg/>" + PNG, "image/png", 422, "not_an_image"),
        (JPEG, "image/png", 422, "not_an_image"),
        (PNG, "image/jpeg", 422, "not_an_image"),
        # A polyglot: a PNG's signature, then an SVG, with no header of a PNG's.
        (
            b"\x89PNG\r\n\x1a\n<svg xmlns='http://www.w3.org/2000/svg'/>",
            "image/png",
            422,
            "not_an_image",
        ),
        (b"\xff\xd8\xff<svg/>", "image/jpeg", 422, "not_an_image"),
        (b"\xff\xd8\xff\xe0\x00", "image/jpeg", 422, "not_an_image"),
        (b"\xff\xd8\xff\xc0\x00\x11\x08", "image/jpeg", 422, "not_an_image"),
        (b"\xff\xd8\xff\xff\xd8\xff\x01\x00\x00\x00", "image/jpeg", 422, "not_an_image"),
        (b"\xff\xd8\xff\xe0\x00\x02<svg/>", "image/jpeg", 422, "not_an_image"),
        # Bombs: a few bytes that every viewer would decode into far more.
        (png(20_000, 20_000), "image/png", 413, "too_many_pixels"),
        (png(9_000, 10), "image/png", 413, "too_many_pixels"),
        (jpeg(5_000, 5_000), "image/jpeg", 413, "too_many_pixels"),
        (png(8_193, 1), "image/png", 413, "too_many_pixels"),
        (png(0, 10), "image/png", 422, "not_an_image"),
        (jpeg(10, 0), "image/jpeg", 422, "not_an_image"),
        (PNG + b"\x00" * MAX_IMAGE, "image/png", 413, "too_large"),
    ],
)
def test_an_image_that_isnt_a_png_or_a_jpeg_or_is_past_its_limit_is_refused(
    client: TestClient, body: bytes, media: str, status: int, kind: str
) -> None:
    _drawn(client)
    refused = _upload(client, body, media)
    assert (refused.status_code, refused.json()["detail"]["type"]) == (status, kind)


def test_a_body_that_grows_past_the_limit_is_refused_whatever_its_length_said(
    client: TestClient,
) -> None:
    _drawn(client)

    def chunks() -> Iterator[bytes]:
        yield PNG
        for _ in range(MAX_IMAGE // 65536 + 2):
            yield b"\x00" * 65536

    refused = client.post(
        "/v1/workspaces/w1/diagrams/d1/images",
        content=chunks(),
        headers={"Content-Type": "image/png", **_as()},
    )
    assert refused.status_code == 413


def test_a_viewer_uploads_nothing_and_off_uploads_nothing_but_reads_stay(
    client: TestClient, toggles: Toggles
) -> None:
    _drawn(client)
    assert _upload(client, user="vera").status_code == 403
    digest = _upload(client).json()["sha256"]
    _named(client, digest, len(PNG), "image/png")
    toggles.off["w1"] = {EXCALIDRAW}
    off = _upload(client)
    assert (off.status_code, off.json()["detail"]["type"]) == (409, "not_enabled")
    read = client.get(f"/v1/workspaces/w1/diagrams/d1/images/{digest}", headers=_as())
    assert read.status_code == 200, "a diagram's images stay readable while diagrams are off"


def test_images_are_kept_apart_by_tenant_workspace_and_diagram(client: TestClient) -> None:
    _drawn(client)
    _drawn(client, workspace="w2")
    _drawn(client, tenant="other")
    digest = _upload(client).json()["sha256"]
    _named(client, digest, len(PNG), "image/png")
    mine = f"/diagrams/d1/images/{digest}"
    assert client.get(f"/v1/workspaces/w1{mine}", headers=_as()).status_code == 200
    # The same digest, asked for from another workspace, another tenant, or another diagram.
    assert client.get(f"/v1/workspaces/w2{mine}", headers=_as()).status_code == 404
    elsewhere = client.get(f"/v1/workspaces/w1{mine}", headers=_as(tenant="other"))
    assert elsewhere.status_code == 404
    assert _upload(client, diagram="d9").status_code == 404
    unknown = client.get(f"/v1/workspaces/w1/diagrams/d9/images/{digest}", headers=_as())
    assert unknown.status_code == 404


def test_uploads_are_paced_per_person(client: TestClient) -> None:
    _drawn(client)
    for at in range(5):
        assert _upload(client, PNG + bytes([at])).status_code == 201
    paced = _upload(client)
    assert (paced.status_code, paced.json()["detail"]["type"]) == (429, "rate_limited")
    assert _upload(client, user="bob").status_code == 201, "another person's pace is their own"


@pytest.mark.parametrize(
    ("blobs", "kind"),
    [
        (InMemoryBlobs(limit=len(PNG) - 1), "too_large"),
        (InMemoryBlobs(workspace_quota=Quota(bytes=len(PNG) - 1)), "over_quota"),
    ],
)
def test_an_image_past_the_stores_limit_or_a_quota_is_refused(
    client: TestClient, kind: str
) -> None:
    _drawn(client)
    refused = _upload(client)
    assert (refused.status_code, refused.json()["detail"]["type"]) == (413, kind)


def test_a_caller_the_actor_resolver_refuses_uploads_nothing(client: TestClient) -> None:
    refused = client.post(
        "/v1/workspaces/w1/diagrams/d1/images",
        content=PNG,
        headers={"Content-Type": "image/png", "x-token": "bad"},
    )
    assert refused.status_code == 401


DOCUMENT = Path(__file__).parents[2] / "schemas" / "artifactr-excalidraw.openapi.json"


def test_the_committed_document_is_the_routers() -> None:
    assert json.loads(DOCUMENT.read_text()) == openapi_document(), "run `moon run artifactr:schema`"


# Running an already-imported module as __main__ is exactly what this test means to do.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_the_module_prints_the_document(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_module("artifactr.excalidraw.openapi", run_name="__main__")
    assert json.loads(capsys.readouterr().out) == openapi_document()


def test_the_documents_application_admits_no_one() -> None:
    with TestClient(openapi_app()) as bare:
        refused = bare.get(f"/workspaces/w1/diagrams/d1/images/{'0' * 64}")
    assert refused.status_code == 401


def test_another_diagram_that_names_the_digest_reads_nothing_of_this_ones(
    client: TestClient,
) -> None:
    _drawn(client)
    _drawn(client, diagram="d2")
    digest = _upload(client).json()["sha256"]
    _named(client, digest, len(PNG), "image/png")
    # d2 names d1's image too, but its bytes were uploaded to d1, so d2 has none to serve.
    _named(client, digest, len(PNG), "image/png", diagram="d2")
    path = "/v1/workspaces/w1/diagrams/{}/images/" + digest
    assert client.get(path.format("d1"), headers=_as()).status_code == 200
    assert client.get(path.format("d2"), headers=_as()).status_code == 404


def test_another_tenant_that_names_the_digest_reads_nothing_of_this_ones(
    client: TestClient,
) -> None:
    _drawn(client)
    _drawn(client, tenant="other")
    digest = _upload(client).json()["sha256"]
    _named(client, digest, len(PNG), "image/png")
    _named(client, digest, len(PNG), "image/png", tenant="other")
    path = f"/v1/workspaces/w1/diagrams/d1/images/{digest}"
    assert client.get(path, headers=_as()).status_code == 200
    theirs = client.get(path, headers=_as(tenant="other"))
    assert theirs.status_code == 404, "the other tenant's d1 names it, but holds no such bytes"


def _answer(response: Any, asked: str) -> tuple[int, Any]:
    """A refusal, with the id it was asked for taken out of what it says."""
    detail = dict(response.json()["detail"])
    assert detail.pop("id", asked) == asked
    return response.status_code, json.loads(json.dumps(detail).replace(asked, "<id>"))


def test_a_hidden_diagram_answers_as_a_missing_one(client: TestClient) -> None:
    _drawn(client)
    digest = _upload(client).json()["sha256"]
    _named(client, digest, len(PNG), "image/png")
    hidden = client.get(f"/v1/workspaces/w1/diagrams/d1/images/{digest}", headers=_as(user="hal"))
    missing = client.get(f"/v1/workspaces/w1/diagrams/d9/images/{digest}", headers=_as(user="hal"))
    # The same answer, but for the id asked for: nothing says d1 is there.
    assert _answer(hidden, "d1") == _answer(missing, "d9")
    assert _answer(_upload(client, user="hal"), "d1") == _answer(
        _upload(client, diagram="d9", user="hal"), "d9"
    )


async def test_bytes_that_arent_an_image_are_never_served_whatever_the_diagram_says(
    client: TestClient, blobs: InMemoryBlobs
) -> None:
    _drawn(client)
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"

    async def body() -> AsyncIterator[bytes]:
        yield svg

    stored = await blobs.put(Scope("tenant", "w1"), "d1", body(), "image/png")
    _named(client, stored.sha256, len(svg), "image/png")
    read = client.get(f"/v1/workspaces/w1/diagrams/d1/images/{stored.sha256}", headers=_as())
    assert read.status_code == 404


def test_an_image_is_served_as_its_own_bytes_say(client: TestClient) -> None:
    _drawn(client)
    digest = _upload(client, JPEG, "image/jpeg").json()["sha256"]
    # The diagram says it is a PNG; its bytes are a JPEG's, and are served as one.
    _named(client, digest, len(JPEG), "image/png")
    read = client.get(f"/v1/workspaces/w1/diagrams/d1/images/{digest}", headers=_as())
    assert read.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize(
    "image",
    [
        png(8_192, 2_048),
        png(4_096, 4_096),
        jpeg(4_096, 4_096),
        # Progressive, its frame SOF2.
        jpeg(640, 480, frame_marker=b"\xc2"),
        # An EXIF segment holding a thumbnail, its own frame inside: the image's frame is read.
        jpeg(640, 480, exif=b"Exif\x00\x00" + jpeg(9_000, 9_000)),
    ],
)
def test_an_image_at_its_limits_or_as_cameras_write_them_is_taken(
    client: TestClient, image: bytes
) -> None:
    _drawn(client)
    media = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
    assert _upload(client, image, media).status_code == 201
