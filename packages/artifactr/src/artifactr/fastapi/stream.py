"""One WebSocket connection speaking the thread protocol."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection, Coroutine
from typing import Any, Final

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, ValidationError
from starlette.requests import HTTPConnection

from artifactr.agent import Runner
from artifactr.core import (
    PROTOCOL,
    ActiveRun,
    CommandFrame,
    CommandResult,
    ErrorFrame,
    EventFrame,
    Forbidden,
    Hello,
    Recorded,
    Rejection,
    ReplayComplete,
    RunId,
    RunStarted,
    ThreadId,
    UnsupportedProtocol,
    ValidationFailed,
    WatchRun,
    Welcome,
    WorkspaceId,
    delivered_to,
    resume,
)
from artifactr.telemetry import Telemetry
from artifactr.telemetry.attributes import CLOSE_CODE, TENANT_ID, WORKSPACE_ID
from artifactr.telemetry.metrics import STREAM_CONNECTIONS, STREAM_DISCONNECTS
from artifactr.workspace import Workspace

logger = logging.getLogger("artifactr.fastapi")

REPLAY_PAGE: Final = 500
"""How many envelopes a stream replays from storage at a time."""

OpenWorkspace = Callable[[HTTPConnection, WorkspaceId], Awaitable[Workspace]]


class Stream:
    """Serves one connection: handshake, replay then live events, commands, live frames.

    One task reads frames; commands run as their own tasks, so a slow command never delays a
    ``stop_run``. Every outgoing frame goes through one bounded outbox and one writer; a client
    too slow to keep up is disconnected (4429) rather than holding events back.

    The connection is traced as an ``artifactr.stream`` span, and counted in
    ``artifactr.stream.connections`` while it is open and ``artifactr.stream.disconnects``, by
    close code, when it ends.
    """

    def __init__(
        self,
        websocket: WebSocket,
        workspace_id: WorkspaceId,
        *,
        open_workspace: OpenWorkspace,
        runner: Runner[Any],
        hello_timeout: float,
        outbox_size: int,
        telemetry: Telemetry,
    ) -> None:
        self._ws = websocket
        self._workspace_id = workspace_id
        self._open_workspace = open_workspace
        self._runner = runner
        self._hello_timeout = hello_timeout
        self._outbox: asyncio.Queue[str] = asyncio.Queue(maxsize=outbox_size)
        self._overflowed = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._watched: set[RunId] = set()
        self._telemetry = telemetry
        self._tenancy: dict[str, str] = {WORKSPACE_ID: workspace_id}
        self._close_code: int | None = None
        self._connected = False

    async def serve(self) -> None:
        """Run the connection until the client leaves."""
        with self._telemetry.tracer.start_as_current_span(
            "artifactr.stream", kind=SpanKind.SERVER, attributes=self._tenancy
        ) as span:
            offered = self._ws.scope.get("subprotocols", [])
            await self._ws.accept(subprotocol=PROTOCOL if PROTOCOL in offered else None)
            try:
                await self._session()
            except WebSocketDisconnect as disconnect:
                self._close_code = self._close_code or disconnect.code
            finally:
                # Recorded before anything is awaited, in case the server cancels this task.
                if self._connected:
                    self._telemetry.add(STREAM_CONNECTIONS, -1, self._tenancy)
                # 1011: the server ended the connection with an error it did not handle.
                code = str(self._close_code or 1011)
                span.set_attribute(CLOSE_CODE, code)
                self._telemetry.add(STREAM_DISCONNECTS, 1, {**self._tenancy, CLOSE_CODE: code})
                for task in self._tasks:
                    task.cancel()
                await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _close(self, code: int, reason: str) -> None:
        self._close_code = self._close_code or code
        await self._ws.close(code=code, reason=reason)

    async def _session(self) -> None:
        try:
            workspace = await self._open_workspace(self._ws, self._workspace_id)
        except HTTPException as refused:  # by the resolver: 4401 unauthenticated, 4400, 4403
            await self._close(4000 + refused.status_code, str(refused.detail))
            return
        except Forbidden as refused:
            await self._close(4403, refused.message)
            return
        self._tenancy[TENANT_ID] = workspace.tenant_id
        hello = await self._hello()
        if hello is None:
            return
        try:
            head = await workspace.head_seq()
            plan = resume(hello, head_seq=head)
            running = await workspace.runs(status="running")
        except Forbidden as refused:  # it may not read the log, or the runs
            await self._close(4403, refused.message)
            return
        except (UnsupportedProtocol, ValidationFailed) as refused:
            await self._close(4400, refused.message)
            return
        self._put(
            Welcome(
                workspace_id=workspace.workspace_id,
                head_seq=head,
                reset=plan.reset,
                active_runs=tuple(ActiveRun(run_id=r.id, thread_id=r.thread_id) for r in running),
            )
        )
        self._connected = True
        self._telemetry.add(STREAM_CONNECTIONS, 1, self._tenancy)
        self._spawn(self._write())
        self._spawn(self._follow(workspace, plan.replay_after, head, hello.threads))
        # Runs that started up to head_seq are watched from this list; later ones as they start.
        for run in running:
            if hello.threads is None or run.thread_id in hello.threads:
                self._watch(workspace, run.id, run.thread_id)
        await self._read(workspace)

    async def _hello(self) -> Hello | None:
        try:
            raw = await asyncio.wait_for(self._ws.receive_text(), self._hello_timeout)
        except TimeoutError:
            await self._close(4408, "hello was not received in time")
            return None
        try:
            return Hello.model_validate_json(raw)
        except ValidationError:
            await self._close(4400, "the first frame must be hello")
            return None

    async def _follow(
        self, workspace: Workspace, after: int, head: int, threads: Collection[ThreadId] | None
    ) -> None:
        # Replay the log up to head a page at a time, then follow it from head. Replay ends at
        # head, not at the last envelope sent: what is hidden from the client leaves gaps.
        while after < head:
            page = await workspace.read(
                after_seq=after, before_seq=head + 1, threads=threads, limit=REPLAY_PAGE
            )
            for envelope in page:
                self._put(EventFrame(**dict(envelope)))
            if len(page) < REPLAY_PAGE:
                break
            after = page[-1].seq
        self._put(ReplayComplete(up_to_seq=head))
        async for envelope in workspace.subscribe(after_seq=head):
            if delivered_to(envelope, threads):
                self._put(EventFrame(**dict(envelope)))
                if isinstance(envelope.event, RunStarted):
                    self._watch(workspace, envelope.event.run_id, envelope.event.thread_id)

    async def _read(self, workspace: Workspace) -> None:
        while True:
            raw = await self._ws.receive_text()
            try:
                frame = CommandFrame.model_validate_json(raw)
            except ValidationError as error:
                first = error.errors(include_url=False)[0]
                self._put(ErrorFrame(message=f"not a command frame: {first['msg']}"))
                continue
            self._spawn(self._handle(workspace, frame))

    async def _handle(self, workspace: Workspace, frame: CommandFrame) -> None:
        try:
            if isinstance(frame.command, WatchRun):
                run = await workspace.run(frame.command.run_id)  # it must belong to this workspace
                self._watch(workspace, run.id, run.thread_id)
                self._put(CommandResult(command_id=frame.command_id, ok=True, outcome=Recorded()))
            else:
                result = await self._runner.execute(
                    workspace, frame.command, command_id=frame.command_id
                )
                self._put(result)
        except Rejection as rejection:
            result = CommandResult(
                command_id=frame.command_id, ok=False, rejection=rejection.payload()
            )
            self._put(result)
        except Exception:
            logger.exception("command %s failed", frame.command_id)
            self._put(ErrorFrame(message=f"command {frame.command_id} failed on the server"))

    def _watch(self, workspace: Workspace, run_id: RunId, thread_id: ThreadId) -> None:
        """Forward a run's live frames until it ends, or its thread is hidden from the client."""
        if run_id in self._watched:
            return
        self._watched.add(run_id)

        async def forward() -> None:
            try:
                async for frame in self._runner.watch(run_id):
                    if thread_id in (await workspace.hidden()).threads:
                        return
                    self._put(frame)
            finally:  # the turn ended: a resumed run's next turn is watched again
                self._watched.discard(run_id)

        self._spawn(forward())

    def _put(self, frame: BaseModel) -> None:
        try:
            self._outbox.put_nowait(frame.model_dump_json())
        except asyncio.QueueFull:
            self._overflowed = True

    async def _write(self) -> None:
        while True:
            text = await self._outbox.get()
            if self._overflowed:
                await self._close(4429, "the client is not keeping up")
                return
            await self._ws.send_text(text)

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
