"""One WebSocket connection speaking the thread protocol."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection, Coroutine
from typing import Any

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
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
    Hello,
    Recorded,
    Rejection,
    ReplayComplete,
    RunId,
    RunStarted,
    ThreadId,
    UnsupportedProtocol,
    WatchRun,
    Welcome,
    WorkspaceId,
    delivered_to,
    resume,
)
from artifactr.workspace import Workspace

logger = logging.getLogger("artifactr.fastapi")

OpenWorkspace = Callable[[HTTPConnection, WorkspaceId], Awaitable[Workspace]]
Execute = Callable[[Workspace, CommandFrame], Awaitable[CommandResult]]


class Stream:
    """Serves one connection: handshake, replay then live events, commands, live frames.

    One task reads frames; commands run as their own tasks, so a slow command never delays a
    ``stop_run``. Every outgoing frame goes through one bounded outbox and one writer; a client
    too slow to keep up is disconnected (4429) rather than holding events back.
    """

    def __init__(
        self,
        websocket: WebSocket,
        workspace_id: WorkspaceId,
        *,
        open_workspace: OpenWorkspace,
        runner: Runner[Any],
        execute: Execute,
        hello_timeout: float,
        outbox_size: int,
    ) -> None:
        self._ws = websocket
        self._workspace_id = workspace_id
        self._open_workspace = open_workspace
        self._runner = runner
        self._execute = execute
        self._hello_timeout = hello_timeout
        self._outbox: asyncio.Queue[str] = asyncio.Queue(maxsize=outbox_size)
        self._overflowed = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._watched: set[RunId] = set()

    async def serve(self) -> None:
        """Run the connection until the client leaves."""
        offered = self._ws.scope.get("subprotocols", [])
        await self._ws.accept(subprotocol=PROTOCOL if PROTOCOL in offered else None)
        try:
            await self._session()
        except WebSocketDisconnect:
            pass
        finally:
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _session(self) -> None:
        try:
            workspace = await self._open_workspace(self._ws, self._workspace_id)
        except HTTPException as refused:
            code = 4401 if refused.status_code == 401 else 4403
            await self._ws.close(code=code, reason=str(refused.detail))
            return
        hello = await self._hello()
        if hello is None:
            return
        head = await workspace.head_seq()
        try:
            plan = resume(hello, head_seq=head)
        except UnsupportedProtocol as unsupported:
            await self._ws.close(code=4400, reason=unsupported.message)
            return
        running = await workspace.runs(status="running")
        self._put(
            Welcome(
                workspace_id=workspace.workspace_id,
                head_seq=head,
                reset=plan.reset,
                active_runs=tuple(ActiveRun(run_id=r.id, thread_id=r.thread_id) for r in running),
            )
        )
        self._spawn(self._write())
        self._spawn(self._follow(workspace, plan.replay_after, head, hello.threads))
        # Runs that started up to head_seq are watched from this list; later ones as they start.
        for run in running:
            if hello.threads is None or run.thread_id in hello.threads:
                self._watch(run.id)
        await self._read(workspace)

    async def _hello(self) -> Hello | None:
        try:
            raw = await asyncio.wait_for(self._ws.receive_text(), self._hello_timeout)
        except TimeoutError:
            await self._ws.close(code=4408, reason="hello was not received in time")
            return None
        try:
            return Hello.model_validate_json(raw)
        except ValidationError:
            await self._ws.close(code=4400, reason="the first frame must be hello")
            return None

    async def _follow(
        self, workspace: Workspace, after: int, head: int, threads: Collection[ThreadId] | None
    ) -> None:
        replaying = after < head
        if not replaying:
            self._put(ReplayComplete(up_to_seq=head))
        # Follow the whole log and filter here, so the end of replay is seen even when the
        # last replayed events belong to threads this client does not follow.
        async for envelope in workspace.subscribe(after_seq=after):
            if delivered_to(envelope, threads):
                self._put(EventFrame(**dict(envelope)))
                if isinstance(envelope.event, RunStarted) and envelope.seq > head:
                    self._watch(envelope.event.run_id)
            if replaying and envelope.seq >= head:
                self._put(ReplayComplete(up_to_seq=head))
                replaying = False

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
                await workspace.run(frame.command.run_id)  # it must belong to this workspace
                self._watch(frame.command.run_id)
                self._put(CommandResult(command_id=frame.command_id, ok=True, outcome=Recorded()))
            else:
                self._put(await self._execute(workspace, frame))
        except Rejection as rejection:
            result = CommandResult(
                command_id=frame.command_id, ok=False, rejection=rejection.payload()
            )
            self._put(result)
        except Exception:
            logger.exception("command %s failed", frame.command_id)
            self._put(ErrorFrame(message=f"command {frame.command_id} failed on the server"))

    def _watch(self, run_id: RunId) -> None:
        if run_id in self._watched:
            return
        self._watched.add(run_id)

        async def forward() -> None:
            async for frame in self._runner.watch(run_id):
                self._put(frame)

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
                await self._ws.close(code=4429, reason="the client is not keeping up")
                return
            await self._ws.send_text(text)

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
