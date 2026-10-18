"""The routes for people's check-out and check-in, beside artifactr's own router.

Every route names a workspace, then an artifact and a version, a check-out or a proposal, never a
bare digest: the artifact is resolved through the workspace first, as the actor, so `authorize`,
the hiding of restricted artifacts and the app's switch all apply before any bytes move.
"""

from collections.abc import Awaitable
from datetime import datetime
from typing import Annotated, Final, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel
from starlette.requests import HTTPConnection

from artifactr.core import Actor, Applied, ArtifactId, Proposed, Rejection, TenantId
from artifactr.fastapi import STATUS_CODES, ResolveActor, Unauthorized
from artifactr.files.app import AppFailed, Failure, Talk
from artifactr.files.blobs import DEFAULT_LIMIT, TooLarge
from artifactr.files.checkouts import Checkout
from artifactr.files.manifest import NativeFile
from artifactr.files.native import NativeFiles
from artifactr.telemetry import annotate, attribution
from artifactr.workspace import ArtifactLease, Workspace, Workspaces
from lattice_core.refusals import refusals

PathId = Annotated[str, Path(min_length=1)]
Version = Annotated[int, Path(ge=1)]

FAILURES: Final[dict[Failure, int]] = {
    "refused": 422,
    "too_large": 413,
    "timeout": 503,
    "crashed": 503,
}
"""The HTTP status for each way the app can fail: the file's fault, or the app's. A page past
the file's end is the app's refusal too, so 422."""

REFUSALS: Final = refusals(400, 401, 403, 404, 409, 413, 422, 503)
"""The refused responses every route documents: artifactr's, a file too large, the app's
refusal, and the app that couldn't finish."""

DOWNLOAD: Final = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox",
    "Cache-Control": "private, no-store",
}
"""What a version's bytes, and its words, are served with: they are an upload, or read from one,
so never sniffed, never run as a page, and never kept by a cache on the way."""

PNG: Final = "image/png"
UNSAID: Final = frozenset(
    {
        "",
        "application/octet-stream",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
        "text/plain",
    }
)
"""The `Content-Type`s that say nothing of a check-in's format: those clients send by default."""
TEXT: Final = "text/plain; charset=utf-8"


class Lease(BaseModel):
    """Who has a native file, until when."""

    checked_out_by: str | None
    """The participant whose check-out holds it, or None for an agent's edit, held for seconds."""
    expires_at: datetime
    checkout_id: str | None = None
    """The check-out's id, only when it is the caller's own: to extend it or check it in, from
    another tab, or after a reload."""


class FileStatus(BaseModel):
    """A native file as a person about to check it out sees it."""

    artifact_id: ArtifactId
    version: int
    name: str
    media_type: str
    size: int
    outline: str
    pages: int | None
    lease: Lease | None
    """Who has it now, if anyone."""
    talk: Talk
    """How much the app talks to the host while a person edits in it: at `save`, the person
    downloads the file, edits it in the app and uploads it again."""
    enabled: bool
    """Whether the app is on in the workspace: off, the file is read but not checked out."""
    limit: int
    """The largest file, in bytes, that a check-in takes."""


class CheckedIn(BaseModel):
    """What a check-in made: a revision, a proposal if it was stale, or nothing."""

    outcome: Literal["applied", "proposed", "unchanged"]
    version: int | None = None
    proposal_id: str | None = None


def files_router(
    workspaces: Workspaces,
    files: NativeFiles,
    *,
    resolve_actor: ResolveActor,
    limit: int = DEFAULT_LIMIT,
) -> APIRouter:
    """Build the router for native files' check-out and check-in, downloads and pages.

    Mount it beside `artifactr_router`, with the same `resolve_actor` and workspaces.

    Args:
        workspaces: Opens tenant-scoped workspaces, and asks their `authorize` hook.
        files: The native files, their stores and their app.
        resolve_actor: Authenticates each request, as for artifactr's router.
        limit: The largest check-in, in bytes, refused from its `Content-Length` before any of
            it is read: give it the blob store's limit, which is 25 MiB unless the store is
            given another. A body that grows past the store's own limit as it streams is
            refused there.
    """
    router = APIRouter(responses=REFUSALS)

    async def workspace_of(request: Request, workspace_id: PathId) -> Workspace:
        async def open_it() -> Workspace:
            tenant_id, actor = await _resolve(resolve_actor, request)
            annotate(attribution(tenant_id=tenant_id, workspace_id=workspace_id, actor=actor))
            return await workspaces.open(tenant_id, workspace_id, actor=actor)

        return await _answered(open_it())

    current_workspace = Depends(workspace_of)

    @router.get("/workspaces/{workspace_id}/files/{artifact_id}")
    async def get_file(artifact_id: PathId, ws: Workspace = current_workspace) -> FileStatus:
        """A native file's head, who has it checked out, and whether it can be."""

        async def status() -> FileStatus:
            head = await ws.get(NativeFile, artifact_id)
            lease = await ws.artifact_lease(artifact_id)
            content = head.data.content
            return FileStatus(
                artifact_id=head.id,
                version=head.version,
                name=head.data.name,
                media_type=content.media_type,
                size=content.size,
                outline=head.data.outline,
                pages=head.data.pages,
                lease=None if lease is None else _lease(lease, ws.actor),
                talk=files.app_of(type(head.data)).talk,
                enabled=await files.enabled(ws, type(head.data)),
                limit=limit,
            )

        return await _answered(status())

    @router.post("/workspaces/{workspace_id}/files/{artifact_id}/checkouts", status_code=201)
    async def check_out(artifact_id: PathId, ws: Workspace = current_workspace) -> Checkout:
        """Check the file out to the actor, holding its lease; then download its head."""
        return await _answered(files.check_out(ws, artifact_id))

    @router.post("/workspaces/{workspace_id}/checkouts/{checkout_id}/extension")
    async def extend(checkout_id: PathId, ws: Workspace = current_workspace) -> Checkout:
        """Extend a check-out by its whole length again, from now."""
        return await _answered(files.extend(ws, checkout_id))

    @router.put(
        "/workspaces/{workspace_id}/checkouts/{checkout_id}/file",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/octet-stream": {}, "*/*": {}},
            }
        },
    )
    async def check_in(
        checkout_id: PathId, request: Request, ws: Workspace = current_workspace
    ) -> CheckedIn:
        """Check the edited file in: its bytes are the body, streamed, and the check-out ends.

        Its `Content-Type` is the file's format, unless it is none, or one a client sends by
        default (`application/octet-stream`, a form's, or `text/plain`): a file in another
        format than the one checked out is refused, never converted.
        """
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            raise HTTPException(status_code=413, detail=f"the file is larger than {limit} bytes")
        given = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        media_type = None if given in UNSAID else given
        outcome = await _answered(
            files.check_in(ws, checkout_id, request.stream(), media_type=media_type)
        )
        if isinstance(outcome, Applied):
            return CheckedIn(outcome="applied", version=outcome.version)
        if isinstance(outcome, Proposed):
            return CheckedIn(outcome="proposed", proposal_id=outcome.proposal_id)
        return CheckedIn(outcome="unchanged")

    @router.get(
        "/workspaces/{workspace_id}/files/{artifact_id}/versions/{version}/content",
        response_class=Response,
        responses={200: {"content": {"application/octet-stream": {}}}},
    )
    async def download(
        artifact_id: PathId, version: Version, ws: Workspace = current_workspace
    ) -> Response:
        """Download a version of the file, as an attachment named as the file is."""

        async def content() -> Response:
            data = await files.read(ws, artifact_id, version=version)
            # A revision keeps the file's name and type, so the head's are every version's.
            head = await ws.get(NativeFile, artifact_id)
            disposition = f"attachment; filename*=UTF-8''{quote(head.data.name, safe='')}"
            return Response(
                data,
                media_type=head.data.content.media_type,
                headers={"Content-Disposition": disposition, **DOWNLOAD},
            )

        return await _answered(content())

    @router.get(
        "/workspaces/{workspace_id}/files/{artifact_id}/versions/{version}/text",
        response_class=Response,
        responses={200: {"content": {TEXT: {}}}},
    )
    async def text(
        artifact_id: PathId, version: Version, ws: Workspace = current_workspace
    ) -> Response:
        """A version's words, as plain text, as the app read them: what a revision's diff shows."""
        words = await _answered(files.read(ws, artifact_id, version=version, part="text"))
        return Response(words, media_type=TEXT, headers=DOWNLOAD)

    @router.get(
        "/workspaces/{workspace_id}/files/{artifact_id}/versions/{version}/pages/{page}",
        response_class=Response,
        responses={200: {"content": {PNG: {}}}},
    )
    async def page(
        artifact_id: PathId,
        version: Version,
        page: Annotated[int, Path(ge=1)],
        ws: Workspace = current_workspace,
    ) -> Response:
        """One page of a version of the file, rendered by the app, as a PNG."""
        png = await _answered(files.render(ws, artifact_id, page, version=version))
        return Response(png, media_type=PNG)

    @router.get(
        "/workspaces/{workspace_id}/proposals/{proposal_id}/text",
        response_class=Response,
        responses={200: {"content": {TEXT: {}}}},
    )
    async def proposed_text(proposal_id: PathId, ws: Workspace = current_workspace) -> Response:
        """The words a proposal would give a native file, as the app read them: its diff."""
        words = await _answered(files.proposed(ws, proposal_id, part="text"))
        return Response(words, media_type=TEXT, headers=DOWNLOAD)

    @router.get(
        "/workspaces/{workspace_id}/proposals/{proposal_id}/pages/{page}",
        response_class=Response,
        responses={200: {"content": {PNG: {}}}},
    )
    async def proposed_page(
        proposal_id: PathId,
        page: Annotated[int, Path(ge=1)],
        ws: Workspace = current_workspace,
    ) -> Response:
        """One page of what a proposal would make of a native file, rendered by the app."""
        png = await _answered(files.render_proposed(ws, proposal_id, page))
        return Response(png, media_type=PNG)

    return router


def _lease(lease: ArtifactLease, actor: Actor) -> Lease:
    """A lease as people see it: whose check-out, never the holder; its id to its own."""
    kind, _, rest = lease.holder.partition(":")
    checkout_id, _, participant = rest.partition(":") if kind == "checkout" else ("", "", "")
    return Lease(
        checked_out_by=participant or None,
        expires_at=lease.expires_at,
        checkout_id=checkout_id if participant == actor.participant else None,
    )


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
        raise HTTPException(status_code=413, detail=str(large)) from large
    except AppFailed as failed:
        detail = {"type": "app_failed", "failure": failed.failure, "message": str(failed)}
        raise HTTPException(status_code=FAILURES[failed.failure], detail=detail) from failed
