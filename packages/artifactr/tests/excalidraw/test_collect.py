"""A diagram's images in native files' blob store, kept by its collection (artifactr ADR-0090)."""

from collections.abc import AsyncIterator
from datetime import timedelta

from pydantic import JsonValue

from artifactr.core import CreateArtifact, Proposed
from artifactr.excalidraw import EXCALIDRAW_TYPES, Diagram
from artifactr.files import WordDocument
from artifactr.files.app import FakeApp
from artifactr.files.blobs import InMemoryBlobs
from artifactr.files.checkouts import InMemoryCheckouts
from artifactr.files.native import NativeFiles
from artifactr.workspace import InMemoryStorage, Scope, Workspaces
from tests.excalidraw.scenes import data, element
from tests.files.clock import FakeClock
from tests.ui.people import ALICE, agent


async def once(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def test_collection_keeps_a_diagrams_images_where_it_is_told_diagrams_name_them() -> None:
    blobs, clock = InMemoryBlobs(clock=FakeClock()), FakeClock()
    workspaces = Workspaces(InMemoryStorage(), types=(*EXCALIDRAW_TYPES, WordDocument))
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    scope = Scope("tenant_a", "ws_1")
    named = await blobs.put(scope, "d1", once(b"picture"), "image/png")
    orphan = await blobs.put(scope, "d1", once(b"never named"), "image/png")
    image = {"sha256": named.sha256, "size": named.size, "media_type": named.media_type}
    with_image = {
        **data(element("img", type="image", fileId=named.sha256)),
        "files": {named.sha256: image},
    }
    await ws.commit(CreateArtifact(kind=Diagram.kind, artifact_id="d1", data=with_image))
    keeping = NativeFiles(blobs, InMemoryCheckouts(), FakeApp(), clock=clock, naming=(Diagram,))
    clock.advance(timedelta(days=2))
    assert await keeping.collect(ws) == 1
    assert await blobs.get(scope, "d1", named.sha256) == b"picture"
    assert await blobs.get(scope, "d1", orphan.sha256) is None


async def test_collection_keeps_what_a_pending_proposal_or_an_archived_diagram_names() -> None:
    blobs, clock = InMemoryBlobs(clock=FakeClock()), FakeClock()
    workspaces = Workspaces(InMemoryStorage(), types=(*EXCALIDRAW_TYPES, WordDocument))
    ws = await workspaces.open("tenant_a", "ws_1", actor=ALICE)
    scope = Scope("tenant_a", "ws_1")

    async def named_by(artifact_id: str, picture: bytes) -> dict[str, JsonValue]:
        blob = await blobs.put(scope, artifact_id, once(picture), "image/png")
        image = {"sha256": blob.sha256, "size": blob.size, "media_type": blob.media_type}
        return {
            **data(element("img", type="image", fileId=blob.sha256)),
            "files": {blob.sha256: image},
        }

    thread = await ws.create_thread("Design")
    proposed = await ws.as_actor(agent(thread.id)).commit(
        CreateArtifact(
            kind=Diagram.kind,
            artifact_id="d2",
            data=await named_by("d2", b"proposed"),
            thread_id=thread.id,
        )
    )
    assert isinstance(proposed, Proposed)
    await ws.commit(
        CreateArtifact(kind=Diagram.kind, artifact_id="d3", data=await named_by("d3", b"old"))
    )
    await ws.commit((await ws.get(Diagram, "d3")).archive())
    keeping = NativeFiles(blobs, InMemoryCheckouts(), FakeApp(), clock=clock, naming=(Diagram,))
    clock.advance(timedelta(days=2))
    assert await keeping.collect(ws) == 0
