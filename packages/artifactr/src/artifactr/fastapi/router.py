"""The router: REST endpoints and the WebSocket stream."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, WebSocket
from fastapi.responses import JSONResponse
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import TracerProvider
from starlette.requests import HTTPConnection

from artifactr.agent import Runner
from artifactr.core import (
    Actor,
    CommandFrame,
    CommandResult,
    Envelope,
    InvalidState,
    Proposal,
    Rejection,
    Revision,
    Run,
    TenantId,
    Thread,
    UnwatchArtifact,
    WatchArtifact,
    WatchRun,
    WorkspaceId,
)
from artifactr.fastapi.presence import LocalPresence, PresenceChannel
from artifactr.fastapi.stream import RECHECK, Stream
from artifactr.telemetry import Telemetry, annotate, attribution
from artifactr.workspace import MAX_COUNT, Workspace, Workspaces
from lattice_core.refusals import Refused, refusals

ResolveActor = Callable[[HTTPConnection], Awaitable[tuple[TenantId, Actor]]]
"""Authenticates a request or connection: returns its tenant and actor, or raises Unauthorized."""

STATUS_CODES: dict[str, int] = {
    "version_conflict": 409,
    "invalid_state": 409,
    "not_enabled": 409,
    "validation_failed": 422,
    "patch_failed": 422,
    "not_found": 404,
    "forbidden": 403,
    "unsupported_protocol": 400,
}
"""The HTTP status for each rejection ``type``."""

REFUSALS: Final = refusals(400, 401, 403, 404, 409, 422)
"""The refused responses every route documents: a malformed request, no or a wrong identity, a
missing thing, a conflict, and a request that does not validate."""


Count = Annotated[int, Query(ge=0, le=MAX_COUNT)]
"""A ``seq`` or a count in a query: as many as storage holds, which the document states."""

PathId = Annotated[str, Path(min_length=1)]
"""An id in a path, which is never empty: ``.../threads/`` would be the list of threads."""


class Unauthorized(Exception):
    """Raise from ``resolve_actor`` to refuse a request (401) or connection (close 4401)."""


def artifactr_router(
    workspaces: Workspaces,
    runner: Runner[Any],
    *,
    resolve_actor: ResolveActor,
    hello_timeout: float = 10.0,
    outbox_size: int = 1000,
    presence: PresenceChannel | None = None,
    watch_recheck: float = RECHECK,
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
) -> APIRouter:
    """Build the router for the thread protocol, REST commands and reads.

    Args:
        workspaces: Opens tenant-scoped workspaces, and asks their ``authorize`` hook about
            each request, command and read.
        runner: Carries out commands, once per ``command_id``, and runs the agent.
        resolve_actor: Authenticates each request and connection.
        hello_timeout: Seconds a new connection has to send ``hello``.
        outbox_size: Frames buffered for a slow connection before it is closed (4429).
        presence: Passes presence between the connections that watch an artifact; by default,
            between this process's own, which serves an application that runs one.
        watch_recheck: Seconds between reads of a watcher's rights, which a lost grant or an
            integration turned off ends a watch within.
        tracer_provider: Where ``artifactr.stream`` spans go. Defaults to the global one.
        meter_provider: Where connection metrics go. Defaults to the global one.

    The span of each REST request in a workspace (FastAPI's own, when it is instrumented) and
    each connection's ``artifactr.stream`` span are attributed to the tenant, workspace and
    actor.
    """
    router = APIRouter(responses=REFUSALS)
    telemetry = Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider)
    rooms = presence if presence is not None else LocalPresence()

    async def resolve(connection: HTTPConnection) -> tuple[TenantId, Actor]:
        """Authenticate a request or connection.

        Raises:
            HTTPException: 401, if ``resolve_actor`` refuses it.
        """
        try:
            return await resolve_actor(connection)
        except Unauthorized as error:
            raise HTTPException(status_code=401, detail=str(error) or "unauthorized") from error

    async def open_workspace(connection: HTTPConnection, workspace_id: WorkspaceId) -> Workspace:
        """Authenticate a request or connection, and open its workspace if it may use it.

        Raises:
            HTTPException: 401, if ``resolve_actor`` refuses it.
            Forbidden: If the workspaces' ``authorize`` refuses the actor this workspace.
        """
        tenant_id, actor = await resolve(connection)
        annotate(attribution(tenant_id=tenant_id, workspace_id=workspace_id, actor=actor))
        return await workspaces.open(tenant_id, workspace_id, actor=actor)

    async def workspace_dependency(request: Request, workspace_id: PathId) -> Workspace:
        return await _or_http(open_workspace(request, workspace_id))

    current_workspace = Depends(workspace_dependency)

    @router.get("/workspaces")
    async def list_workspaces(
        request: Request, after: str | None = None, limit: Annotated[int, Query(ge=1)] = 100
    ) -> list[WorkspaceId]:
        """Return a page of the caller's tenant's workspaces that the caller may open, by id.

        Pass the last id as ``after`` for the next page; a page shorter than ``limit`` is the
        last.
        """
        tenant_id, actor = await resolve(request)
        return await _or_http(workspaces.list(tenant_id, actor=actor, after=after, limit=limit))

    @router.post(
        "/workspaces/{workspace_id}/commands",
        responses={
            status: {"model": CommandResult | Refused, "description": "Refused, or rejected"}
            for status in STATUS_CODES.values()
        },
    )
    async def post_command(
        frame: CommandFrame, response: Response, workspace: Workspace = current_workspace
    ) -> CommandResult:
        """Submit one command. The body is the same frame as over the WebSocket."""
        if isinstance(frame.command, WatchRun | WatchArtifact | UnwatchArtifact):
            refused = InvalidState(f"{frame.command.type} needs a WebSocket")
            result = CommandResult(
                command_id=frame.command_id, ok=False, rejection=refused.payload()
            )
        else:
            result = await runner.execute(workspace, frame.command, command_id=frame.command_id)
        if result.rejection is not None:
            response.status_code = STATUS_CODES.get(str(result.rejection["type"]), 400)
        return result

    @router.get("/workspaces/{workspace_id}/artifacts")
    async def list_artifacts(
        kind: str | None = None,
        include_archived: bool = False,
        workspace: Workspace = current_workspace,
    ) -> JSONResponse:
        """List current artifacts, optionally of one kind."""
        artifacts = await _or_http(
            workspace.artifacts(kind=kind, include_archived=include_archived)
        )
        return JSONResponse([a.model_dump(mode="json") for a in artifacts])

    @router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: PathId, workspace: Workspace = current_workspace
    ) -> JSONResponse:
        """Return an artifact's current version."""
        artifact = await _or_http(workspace.artifact(artifact_id))
        return JSONResponse(artifact.model_dump(mode="json"))

    @router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/revisions")
    async def list_revisions(
        artifact_id: PathId, workspace: Workspace = current_workspace
    ) -> list[Revision]:
        """Return an artifact's revisions, oldest first."""
        return await _or_http(workspace.revisions(artifact_id))

    @router.get("/workspaces/{workspace_id}/events")
    async def list_events(
        after_seq: Count = 0,
        before_seq: Count | None = None,
        thread_id: Annotated[list[str] | None, Query()] = None,
        limit: Count | None = None,
        last: Count | None = None,
        workspace: Workspace = current_workspace,
    ) -> list[Envelope]:
        """Return a page of the log, optionally for some threads. ``thread_id`` may repeat.

        The window is ``after_seq < seq < before_seq``. ``limit`` returns its first envelopes,
        ``last`` its last ones, oldest first either way.
        """
        return await _or_http(
            workspace.read(
                after_seq=after_seq,
                before_seq=before_seq,
                threads=thread_id,
                limit=limit,
                last=last,
            )
        )

    @router.get("/workspaces/{workspace_id}/threads")
    async def list_threads(workspace: Workspace = current_workspace) -> list[Thread]:
        """Return every thread, oldest first."""
        return await _or_http(workspace.threads())

    @router.get("/workspaces/{workspace_id}/threads/{thread_id}")
    async def get_thread(thread_id: PathId, workspace: Workspace = current_workspace) -> Thread:
        """Return a thread, with its mode and focus."""
        return await _or_http(workspace.thread(thread_id))

    @router.get("/workspaces/{workspace_id}/proposals")
    async def list_proposals(
        status: Literal["pending", "accepted", "rejected"] | None = "pending",
        workspace: Workspace = current_workspace,
    ) -> list[Proposal]:
        """Return proposals with a status, pending by default."""
        return await _or_http(workspace.proposals(status=status))

    @router.get("/workspaces/{workspace_id}/runs/{run_id}")
    async def get_run(run_id: PathId, workspace: Workspace = current_workspace) -> Run:
        """Return a run, with any requests it is paused on."""
        return await _or_http(workspace.run(run_id))

    @router.websocket("/workspaces/{workspace_id}/stream")
    async def stream(websocket: WebSocket, workspace_id: WorkspaceId) -> None:
        """The thread protocol: a resumable subscription to the log, commands and live frames."""
        await Stream(
            websocket,
            workspace_id,
            open_workspace=open_workspace,
            runner=runner,
            hello_timeout=hello_timeout,
            outbox_size=outbox_size,
            telemetry=telemetry,
            presence=rooms,
            recheck=watch_recheck,
        ).serve()

    return router


async def _or_http[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except Rejection as rejection:
        status = STATUS_CODES.get(rejection.code, 400)
        raise HTTPException(status_code=status, detail=rejection.payload()) from rejection
