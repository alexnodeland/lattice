"""The routes for the images a person puts on a diagram's canvas, beside artifactr's own router.

A person's canvas uploads an image as they put it on a diagram, and names it in the diagram by
its digest, as the agent's drawings do (artifactr ADR-0092). Every route names a workspace and a
diagram, never a bare digest: the diagram is read through the workspace first, as the actor, so
``authorize``, the hiding of restricted artifacts and the ``excalidraw`` switch all apply before
any bytes move. An image is a PNG or a JPEG, by its own first bytes as by what it says it is, and
at most :data:`MAX_IMAGE`, and at most :data:`MAX_SIDE` pixels a side and :data:`MAX_PIXELS` in
all, as its header says: an SVG, which can run script and reach out, is never taken, nor an image
small in bytes that every viewer would decode into far more.

An image uploaded and never named by a revision is kept only until the native files' collection,
told of diagrams (``NativeFiles(naming=(Diagram,))``), removes what no revision names.
"""

from collections.abc import AsyncIterator, Awaitable
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from starlette.requests import HTTPConnection

from artifactr.core import Actor, NotEnabled, Rejection, TenantId
from artifactr.excalidraw.integrations import EXCALIDRAW
from artifactr.excalidraw.types import Diagram, DiagramFile
from artifactr.fastapi import STATUS_CODES, ResolveActor, Unauthorized
from artifactr.files.blobs import Blobs, OverQuota, TooLarge
from artifactr.files.fastapi.pace import Pace
from artifactr.telemetry import annotate, attribution
from artifactr.workspace import Access, Scope, Workspace, Workspaces
from lattice_core.integrations import Defaults, Integrations
from lattice_core.refusals import refusals

__all__ = ["MAX_IMAGE", "MAX_PIXELS", "MAX_SIDE", "diagrams_router"]

MAX_IMAGE: Final = 2 * 1024 * 1024
"""The largest image a person may put on a diagram, in bytes: as large as a conversion's."""

MAX_SIDE: Final = 8192
"""The most pixels an image's side may be."""

MAX_PIXELS: Final = 4096 * 4096
"""The most pixels an image may be, width times height: 64 MiB decoded at four bytes a pixel, 128
MiB at eight, as a 16-bit PNG with alpha is."""

SIGNATURES: Final[dict[str, bytes]] = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}
"""The images a canvas takes, by their type, and the first bytes each begins with."""

SERVED: Final = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox",
    "Cache-Control": "private, max-age=86400, immutable",
}
"""What an image's bytes are served with: an upload, so never sniffed and never run as a page.
Its digest names it, so a browser may keep it."""

EDIT: Final = "artifactr:edit_artifact"
"""The action an upload needs: the person may edit the diagram."""

Digest = Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")]
PathId = Annotated[str, Path(min_length=1, max_length=128)]
REFUSALS: Final = refusals(400, 401, 403, 404, 409, 413, 415, 422, 429)


def diagrams_router(
    workspaces: Workspaces,
    blobs: Blobs,
    *,
    resolve_actor: ResolveActor,
    integrations: Integrations | None = None,
    uploads_per_minute: int = 30,
) -> APIRouter:
    """Build the router for a diagram's images: put on its canvas by a person, and read back.

    Mount it beside `artifactr_router`, with the same `resolve_actor` and workspaces, and the
    native files' blob store, which their collection keeps diagrams' images in.

    Args:
        workspaces: Opens tenant-scoped workspaces, and asks their `authorize` hook.
        blobs: Where the images are kept: the native files' store.
        resolve_actor: Authenticates each request, as for artifactr's router.
        integrations: Whether diagrams are on in a workspace: lattice-core's defaults, where
            they are off, unless given.
        uploads_per_minute: How many images each person of a tenant may upload in a minute, in
            this process, past which one is refused with 429.
    """
    router = APIRouter(responses=REFUSALS)
    switches = integrations or Defaults()
    pace = Pace(uploads_per_minute)

    async def workspace_of(request: Request, workspace_id: PathId) -> Workspace:
        async def open_it() -> Workspace:
            tenant_id, actor = await _resolve(resolve_actor, request)
            annotate(attribution(tenant_id=tenant_id, workspace_id=workspace_id, actor=actor))
            return await workspaces.open(tenant_id, workspace_id, actor=actor)

        return await _answered(open_it())

    current_workspace = Depends(workspace_of)

    @router.post(
        "/workspaces/{workspace_id}/diagrams/{artifact_id}/images",
        status_code=201,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {media: {} for media in SIGNATURES},
            }
        },
    )
    async def upload(
        request: Request, artifact_id: PathId, ws: Workspace = current_workspace
    ) -> DiagramFile:
        """Upload an image to put on a diagram: a PNG or a JPEG, at most 2 MiB, by its bytes.

        Its answer names it as the diagram will: by its digest, which an edit's `files` adds.
        """
        media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type not in SIGNATURES:
            raise _refused(415, "unsupported", "an image on a canvas is a PNG or a JPEG")
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_IMAGE:
            raise _refused(413, "too_large", f"an image is at most {MAX_IMAGE} bytes")

        async def taken() -> DiagramFile:
            await _editable(ws, artifact_id, switches)
            if (wait := pace.admit((ws.tenant_id, ws.actor.participant))) is not None:
                raise HTTPException(
                    status_code=429,
                    detail={"type": "rate_limited", "message": "too many images: wait a minute"},
                    headers={"Retry-After": str(wait)},
                )
            data = await _read(request)
            size = _size(data) if _sniffed(data) == media_type else None
            if size is None:
                raise _refused(422, "not_an_image", f"the bytes aren't a {media_type}")
            width, height = size
            if not width or not height:
                raise _refused(422, "not_an_image", "the image has no pixels")
            if max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
                raise _refused(
                    413,
                    "too_many_pixels",
                    f"an image is at most {MAX_SIDE} pixels a side and {MAX_PIXELS} in all",
                )
            blob = await blobs.put(
                Scope(ws.tenant_id, ws.workspace_id), artifact_id, _once(data), media_type
            )
            return DiagramFile(sha256=blob.sha256, size=blob.size, media_type=blob.media_type)

        return await _answered(taken())

    @router.get(
        "/workspaces/{workspace_id}/diagrams/{artifact_id}/images/{sha256}",
        response_class=Response,
        responses={200: {"content": {media: {} for media in SIGNATURES}}},
    )
    async def image(
        artifact_id: PathId, sha256: Digest, ws: Workspace = current_workspace
    ) -> Response:
        """An image the diagram names, by its digest, as its canvas shows it."""

        async def read() -> Response:
            diagram = await ws.get(Diagram, artifact_id)
            named = diagram.data.files.get(sha256)
            data = None
            if named is not None:
                data = await blobs.get(Scope(ws.tenant_id, ws.workspace_id), artifact_id, sha256)
            # Served as what its own bytes are, whatever the diagram says it is.
            served = None if data is None else _sniffed(data)
            if named is None or data is None or served is None:
                raise _refused(404, "not_found", "the diagram names no such image")
            return Response(data, media_type=served, headers=SERVED)

        return await _answered(read())

    return router


async def _editable(ws: Workspace, artifact_id: str, switches: Integrations) -> None:
    """Refuse an upload to a diagram the person can't edit, or while diagrams are off."""
    await ws.get(Diagram, artifact_id)  # it is there, and theirs to see
    await ws.check(Access(action=EDIT, artifact_id=artifact_id))
    if not await switches.is_enabled(ws.tenant_id, ws.workspace_id, EXCALIDRAW):
        raise NotEnabled(EXCALIDRAW)


async def _read(request: Request) -> bytes:
    """The body, refused as it grows past an image's limit, whatever its length said."""
    read = bytearray()
    async for chunk in request.stream():
        read += chunk
        if len(read) > MAX_IMAGE:
            raise _refused(413, "too_large", f"an image is at most {MAX_IMAGE} bytes")
    return bytes(read)


def _sniffed(data: bytes) -> str | None:
    """The type an image's own first bytes say it is, or None for neither a PNG nor a JPEG."""
    return next((media for media, first in SIGNATURES.items() if data.startswith(first)), None)


_SOF: Final = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
"""A JPEG's start-of-frame markers, which hold its size; the rest of 0xC0 to 0xCF are not."""


def _size(data: bytes) -> tuple[int, int] | None:
    """An image's width and height, as its header says, or None where it says none.

    A PNG's is its first chunk, ``IHDR``; a JPEG's, its first start-of-frame segment.
    """
    if data.startswith(SIGNATURES["image/png"]):
        if len(data) < 24 or data[12:16] != b"IHDR":
            return None
        return int.from_bytes(data[16:20]), int.from_bytes(data[20:24])
    at = 2
    while at + 4 <= len(data):
        if data[at] != 0xFF:
            return None
        marker = data[at + 1]
        if marker == 0xFF:  # fill
            at += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:  # no length
            at += 2
            continue
        if marker in _SOF:
            if at + 9 > len(data):
                return None
            return int.from_bytes(data[at + 7 : at + 9]), int.from_bytes(data[at + 5 : at + 7])
        at += 2 + int.from_bytes(data[at + 2 : at + 4])
    return None


async def _once(data: bytes) -> AsyncIterator[bytes]:
    yield data


def _refused(status: int, kind: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"type": kind, "message": message})


async def _resolve(
    resolve_actor: ResolveActor, connection: HTTPConnection
) -> tuple[TenantId, Actor]:
    try:
        return await resolve_actor(connection)
    except Unauthorized as error:
        raise HTTPException(status_code=401, detail=str(error) or "unauthorized") from error


async def _answered[T](awaitable: Awaitable[T]) -> T:
    """The awaitable's result, or its refusal as an HTTP error."""
    try:
        return await awaitable
    except Rejection as rejection:
        status = STATUS_CODES.get(rejection.code, 400)
        raise HTTPException(status_code=status, detail=rejection.payload()) from rejection
    except TooLarge as large:
        detail = {"type": "too_large", "message": str(large)}
        raise HTTPException(status_code=413, detail=detail) from large
    except OverQuota as over:
        detail = {
            "type": "over_quota",
            "message": f"the {over.over} quota, {over.limit}, is reached",
            "quota": over.over,
            "limit": over.limit,
        }
        raise HTTPException(status_code=413, detail=detail) from over
