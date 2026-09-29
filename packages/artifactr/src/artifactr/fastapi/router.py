"""The router: REST endpoints and the WebSocket stream."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket
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
    Proposal,
    Rejection,
    Revision,
    Run,
    TenantId,
    Thread,
    WatchRun,
    WorkspaceId,
)
from artifactr.fastapi.stream import Stream
from artifactr.telemetry import Telemetry, annotate, attribution
from artifactr.workspace import Authorize, Workspace, Workspaces

ResolveActor = Callable[[HTTPConnection], Awaitable[tuple[TenantId, Actor]]]
"""Authenticates a request or connection: returns its tenant and actor, or raises Unauthorized."""

STATUS_CODES: dict[str, int] = {
    "version_conflict": 409,
    "invalid_state": 409,
    "validation_failed": 422,
    "patch_failed": 422,
    "not_found": 404,
    "forbidden": 403,
    "unsupported_protocol": 400,
}
"""The HTTP status for each rejection ``type``."""


class Unauthorized(Exception):
    """Raise from ``resolve_actor`` to refuse a request (401) or connection (close 4401)."""


def artifactr_router(
    workspaces: Workspaces,
    runner: Runner[Any],
    *,
    resolve_actor: ResolveActor,
    authorize: Authorize | None = None,
    hello_timeout: float = 10.0,
    outbox_size: int = 1000,
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
) -> APIRouter:
    """Build the router for the thread protocol, REST commands and reads.

    Args:
        workspaces: Opens tenant-scoped workspaces.
        runner: Carries out commands, once per ``command_id``, and runs the agent.
        resolve_actor: Authenticates each request and connection.
        authorize: Whether an actor may use a workspace; allows everything if omitted.
        hello_timeout: Seconds a new connection has to send ``hello``.
        outbox_size: Frames buffered for a slow connection before it is closed (4429).
        tracer_provider: Where ``artifactr.stream`` spans go. Defaults to the global one.
        meter_provider: Where connection metrics go. Defaults to the global one.

    Each REST request's span (FastAPI's own, when it is instrumented) and each connection's
    ``artifactr.stream`` span are attributed to the tenant, workspace and actor.
    """
    router = APIRouter()
    telemetry = Telemetry(tracer_provider=tracer_provider, meter_provider=meter_provider)

    async def open_workspace(connection: HTTPConnection, workspace_id: WorkspaceId) -> Workspace:
        try:
            tenant_id, actor = await resolve_actor(connection)
        except Unauthorized as error:
            raise HTTPException(status_code=401, detail=str(error) or "unauthorized") from error
        annotate(attribution(tenant_id=tenant_id, workspace_id=workspace_id, actor=actor))
        if authorize is not None and not await authorize(tenant_id, workspace_id, actor):
            raise HTTPException(status_code=403, detail="this workspace is not yours to use")
        return await workspaces.open(tenant_id, workspace_id, actor=actor)

    async def workspace_dependency(request: Request, workspace_id: WorkspaceId) -> Workspace:
        return await open_workspace(request, workspace_id)

    current_workspace = Depends(workspace_dependency)

    async def execute(workspace: Workspace, frame: CommandFrame) -> CommandResult:
        if isinstance(frame.command, WatchRun):
            return CommandResult(
                command_id=frame.command_id,
                ok=False,
                rejection={"type": "invalid_state", "message": "watch_run needs a WebSocket"},
            )
        return await runner.execute_once(workspace, frame.command, command_id=frame.command_id)

    @router.post("/workspaces/{workspace_id}/commands")
    async def post_command(
        frame: CommandFrame, response: Response, workspace: Workspace = current_workspace
    ) -> CommandResult:
        """Submit one command. The body is the same frame as over the WebSocket."""
        result = await execute(workspace, frame)
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
        artifacts = await workspace.artifacts(include_archived=include_archived)
        return JSONResponse(
            [a.model_dump(mode="json") for a in artifacts if kind is None or a.kind == kind]
        )

    @router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: str, workspace: Workspace = current_workspace
    ) -> JSONResponse:
        """Return an artifact's current version."""
        artifact = await _or_http(workspace.artifact(artifact_id))
        return JSONResponse(artifact.model_dump(mode="json"))

    @router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/revisions")
    async def list_revisions(
        artifact_id: str, workspace: Workspace = current_workspace
    ) -> list[Revision]:
        """Return an artifact's revisions, oldest first."""
        await _or_http(workspace.artifact(artifact_id))
        return await workspace.revisions(artifact_id)

    @router.get("/workspaces/{workspace_id}/events")
    async def list_events(
        after_seq: int = 0,
        before_seq: int | None = None,
        thread_id: Annotated[list[str] | None, Query()] = None,
        limit: int | None = None,
        last: int | None = None,
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
        return await workspace.threads()

    @router.get("/workspaces/{workspace_id}/threads/{thread_id}")
    async def get_thread(thread_id: str, workspace: Workspace = current_workspace) -> Thread:
        """Return a thread, with its mode and focus."""
        return await _or_http(workspace.thread(thread_id))

    @router.get("/workspaces/{workspace_id}/proposals")
    async def list_proposals(
        status: Literal["pending", "accepted", "rejected"] | None = "pending",
        workspace: Workspace = current_workspace,
    ) -> list[Proposal]:
        """Return proposals with a status, pending by default."""
        return await workspace.proposals(status=status)

    @router.get("/workspaces/{workspace_id}/runs/{run_id}")
    async def get_run(run_id: str, workspace: Workspace = current_workspace) -> Run:
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
            execute=execute,
            hello_timeout=hello_timeout,
            outbox_size=outbox_size,
            telemetry=telemetry,
        ).serve()

    return router


async def _or_http[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except Rejection as rejection:
        status = STATUS_CODES.get(rejection.code, 400)
        raise HTTPException(status_code=status, detail=rejection.payload()) from rejection
