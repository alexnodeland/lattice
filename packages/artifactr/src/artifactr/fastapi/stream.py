"""One WebSocket connection speaking the thread protocol."""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Collection, Coroutine
from datetime import datetime
from typing import Annotated, Any, Final, Literal

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.requests import HTTPConnection

from artifactr.agent import Runner
from artifactr.core import (
    PROTOCOL,
    ActiveRun,
    ArtifactId,
    CommandFrame,
    CommandResult,
    ErrorFrame,
    EventFrame,
    Forbidden,
    Hello,
    InvalidState,
    PeerLeft,
    PeerPresence,
    Presence,
    Recorded,
    Rejection,
    ReplayComplete,
    RunId,
    RunStarted,
    ThinkingDelta,
    ThreadId,
    UnsupportedProtocol,
    UnwatchArtifact,
    ValidationFailed,
    WatchArtifact,
    Watching,
    WatchRun,
    Welcome,
    WorkspaceId,
    delivered_to,
    resume,
)
from artifactr.core.protocol import MAX_PRESENCE
from artifactr.fastapi.presence import LocalPresence, PresenceChannel, Room
from artifactr.telemetry import Telemetry
from artifactr.telemetry.attributes import CLOSE_CODE, TENANT_ID, WORKSPACE_ID
from artifactr.telemetry.metrics import STREAM_CONNECTIONS, STREAM_DISCONNECTS
from artifactr.workspace import Workspace

logger = logging.getLogger("artifactr.fastapi")

REPLAY_PAGE: Final = 500
"""How many envelopes a stream replays from storage at a time."""

OpenWorkspace = Callable[[HTTPConnection, WorkspaceId], Awaitable[Workspace]]

PRESENCE_PER_SECOND: Final = 30
"""The most presence frames a connection may send a second, across what it watches."""

MOST_WATCHED: Final = 20
"""The most artifacts one connection may watch at once."""

RECHECK: Final = 30.0
"""Seconds between reads of a watcher's rights, which live outside the log (lattice RFC-0006)."""

LIVE_WAIT: Final = 30.0
"""Seconds a run's live frame waits for room in the outbox before the client is closed (4429)."""

OUTBOX_RESERVE: Final = 10
"""The outbox's share, as ``1/OUTBOX_RESERVE``, kept free of live frames for events and results."""

_INBOUND: Final = TypeAdapter[CommandFrame | Presence](
    Annotated[CommandFrame | Presence, Field(discriminator="type")]
)
"""A client's frame after hello: a command, or presence."""

_ENDED: Final = "a watch ended: the artifact can't be watched now"
"""What a watcher is told as its watch ends; its UI says it in its own words."""


class _Watch:
    """One artifact this connection watches: its room, and what the watcher may do there."""

    def __init__(
        self, room: Room, rights: Literal["view", "edit"], recheck: asyncio.Task[None]
    ) -> None:
        self.room = room
        self.rights = rights
        self.recheck = recheck
        self.warned = False
        self.peers: set[str] = set()
        """The peers it has been told are here, to tell they left if the watch ends."""


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
        presence: PresenceChannel | None = None,
        recheck: float = RECHECK,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ws = websocket
        self._workspace_id = workspace_id
        self._open_workspace = open_workspace
        self._runner = runner
        self._hello_timeout = hello_timeout
        self._outbox: asyncio.Queue[str] = asyncio.Queue(maxsize=outbox_size)
        self._overflowed = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._watched: dict[RunId, int] = {}
        """Each run forwarded, by the latest turn: the ``seq`` of its ``run_started``, or 0."""
        self._telemetry = telemetry
        self._tenancy: dict[str, str] = {WORKSPACE_ID: workspace_id}
        self._close_code: int | None = None
        self._connected = False
        # Without a channel, the connection is alone in its rooms: it is told of no one.
        self._presence = presence if presence is not None else LocalPresence()
        self._recheck = recheck
        self._clock = clock
        self._peer = uuid.uuid4().hex
        """This connection, as its peers know it: opaque, and new each time it connects."""
        self._watches: dict[ArtifactId, _Watch] = {}
        self._peers: dict[tuple[str, ArtifactId], str] = {}
        """Presence to send: each peer's latest frame for each artifact, sent after events."""
        self._wake = asyncio.Event()
        self._room = asyncio.Event()
        """Set by the writer each time it takes a frame from the outbox: room for a live frame."""
        self._heard: list[float] = []
        """When this connection's last presence frames arrived, for its pace."""
        self._paced = 0.0
        """When it was last told its presence was dropped for its pace: once a second at most."""

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
                for artifact_id in list(self._watches):
                    self._unwatch(artifact_id)
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
        # Each followed run's latest turn: where its run_started is, and when it was. It is
        # read back from the run's thread, so a run the client doesn't follow isn't read.
        followed = [r for r in running if hello.threads is None or r.thread_id in hello.threads]
        starts = {run.id: await _started(workspace, run.id, run.thread_id) for run in followed}
        self._put(
            Welcome(
                workspace_id=workspace.workspace_id,
                head_seq=head,
                reset=plan.reset,
                active_runs=tuple(
                    ActiveRun(
                        run_id=r.id,
                        thread_id=r.thread_id,
                        started_at=starts[r.id][1] if r.id in starts else None,
                    )
                    for r in running
                ),
            )
        )
        self._connected = True
        self._telemetry.add(STREAM_CONNECTIONS, 1, self._tenancy)
        self._spawn(self._write())
        if hello.events:
            self._spawn(self._follow(workspace, plan.replay_after, head, hello.threads))
            # Runs running as the client joined are watched from this list, each as the turn
            # its latest run_started began, so that run_started, if the log has it after
            # head_seq, is the same turn and not watched twice; later turns as they start.
            for run in followed:
                self._watch(workspace, run.id, run.thread_id, turn=starts[run.id][0])
        else:
            self._put(ReplayComplete(up_to_seq=head))  # for presence alone: no events
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
                    run, thread = envelope.event.run_id, envelope.event.thread_id
                    self._watch(workspace, run, thread, turn=envelope.seq)

    async def _read(self, workspace: Workspace) -> None:
        while True:
            raw = await self._ws.receive_text()
            try:
                frame = _INBOUND.validate_json(raw)
            except ValidationError as error:
                first = error.errors(include_url=False)[0]
                self._put(ErrorFrame(message=f"not a command or presence frame: {first['msg']}"))
                continue
            if isinstance(frame, Presence):
                self._said(workspace, frame, len(raw))
            else:
                self._spawn(self._handle(workspace, frame))

    def _said(self, workspace: Workspace, frame: Presence, size: int) -> None:
        """Pass on a presence frame to the artifact's other watchers, or drop it.

        Dropped: one past :data:`MAX_PRESENCE` characters of JSON, or past the pace, with an
        ``error`` at most once a second; one for an artifact not watched here, silently;
        ``editing`` from a watcher who may only view, with one ``error``.
        """
        now = self._clock()
        self._heard = [at for at in self._heard if now - at < 1.0]
        if size > MAX_PRESENCE or len(self._heard) >= PRESENCE_PER_SECOND:
            if now - self._paced >= 1.0:
                self._paced = now
                self._put(ErrorFrame(message="presence dropped: too large, or too many a second"))
            return
        self._heard.append(now)
        watch = self._watches.get(frame.artifact_id)
        if watch is None:
            return
        if frame.editing and watch.rights != "edit":
            if not watch.warned:
                watch.warned = True
                self._put(ErrorFrame(message="presence dropped: this watch may only view"))
            return
        fields = frame.model_dump(exclude={"type"})
        said = PeerPresence(**fields, peer=self._peer, actor=workspace.actor)
        self._presence.say(watch.room, said)

    async def _handle(self, workspace: Workspace, frame: CommandFrame) -> None:
        try:
            command = frame.command
            if isinstance(command, WatchRun):
                run = await workspace.run(command.run_id)  # it must belong to this workspace
                self._watch(workspace, run.id, run.thread_id)
                self._put(CommandResult(command_id=frame.command_id, ok=True, outcome=Recorded()))
            elif isinstance(command, WatchArtifact):
                watching = await self._watch_artifact(workspace, command.artifact_id)
                self._put(CommandResult(command_id=frame.command_id, ok=True, outcome=watching))
            elif isinstance(command, UnwatchArtifact):
                self._unwatch(command.artifact_id)
                self._put(CommandResult(command_id=frame.command_id, ok=True, outcome=Recorded()))
            else:
                result = await self._runner.execute(workspace, command, command_id=frame.command_id)
                self._put(result)
        except Rejection as rejection:
            result = CommandResult(
                command_id=frame.command_id, ok=False, rejection=rejection.payload()
            )
            self._put(result)
        except Exception:
            logger.exception("command %s failed", frame.command_id)
            self._put(ErrorFrame(message=f"command {frame.command_id} failed on the server"))

    def _watch(
        self, workspace: Workspace, run_id: RunId, thread_id: ThreadId, *, turn: int = 0
    ) -> None:
        """Forward a run's live frames until its turn ends, or its thread is hidden.

        A run that paused and resumed is watched again for its new turn, the ``seq`` of the
        ``run_started`` that began it; a turn already watched isn't watched twice, and 0, a run a
        client asks to watch, is whatever turn it is in. A turn's forwarder ends as its turn does.
        """
        if self._watched.get(run_id, -1) >= turn:
            return
        self._watched[run_id] = turn

        async def forward() -> None:
            async for frame in self._runner.watch(run_id):
                if thread_id in (await workspace.hidden()).threads:
                    return
                if isinstance(frame.event, ThinkingDelta) and self._crowded():
                    continue  # thinking goes first: it is never kept, and the reply matters more
                await self._put_waiting(frame)

        self._spawn(forward())

    async def _watch_artifact(self, workspace: Workspace, artifact_id: ArtifactId) -> Watching:
        """Watch an artifact: checked as a read, then the others there sent, latest first."""
        rights = await workspace.watch(artifact_id)
        watching = Watching(artifact_id=artifact_id, rights=rights, peer=self._peer)
        current = self._watches.get(artifact_id)
        if current is not None:
            current.rights = rights
            return watching
        if len(self._watches) >= MOST_WATCHED:
            raise InvalidState(f"one connection watches at most {MOST_WATCHED} artifacts")
        room = (workspace.tenant_id, workspace.workspace_id, artifact_id)
        here = self._presence.join(room, self._peer, self._told)  # a full room refuses it
        recheck = asyncio.create_task(self._rechecked(workspace, artifact_id))
        self._watches[artifact_id] = _Watch(room, rights, recheck)
        for frame in here:
            self._told(frame)
        return watching

    async def _rechecked(self, workspace: Workspace, artifact_id: ArtifactId) -> None:
        """Read a watcher's rights again every :data:`RECHECK` seconds.

        The watch ends once they are gone: a grant lost, an integration turned off, or the
        artifact hidden, none of which the log says.
        """
        while True:  # until it ends here, or is cancelled as the watch is unwatched
            await asyncio.sleep(self._recheck)
            try:
                # A grants store that doesn't answer in time is one that can't be read.
                async with asyncio.timeout(self._recheck):
                    rights = await workspace.watch(artifact_id)
            except Rejection:
                self._end(artifact_id)
                return
            except Exception as error:
                # Its rights can't be read: it fails closed, never watching on unchecked.
                logger.warning("a watch's rights couldn't be read: %s", type(error).__name__)
                self._end(artifact_id)
                return
            self._watches[artifact_id].rights = rights

    def _end(self, artifact_id: ArtifactId) -> None:
        """End a watch the watcher may no longer hold: every peer leaves it, and so does it.

        Its own ``peer_left`` is what says its watch ended; an ``error`` says so to a client that
        doesn't read it.
        """
        # Those it was told are here, and those it is yet to be told of, who leave as it does.
        waiting = {peer for peer, watched in self._peers if watched == artifact_id}
        peers = self._watches[artifact_id].peers | waiting
        self._unwatch(artifact_id)
        for peer in [*sorted(peers), self._peer]:
            self._told(PeerLeft(artifact_id=artifact_id, peer=peer))
        self._put(ErrorFrame(message=_ENDED))

    def _unwatch(self, artifact_id: ArtifactId) -> None:
        watch = self._watches.pop(artifact_id, None)
        if watch is None:
            return
        watch.recheck.cancel()
        # What it was yet to be sent of the others there still goes: it says nothing new.
        self._presence.leave(watch.room, self._peer)

    def _told(self, frame: PeerPresence | PeerLeft, text: str | None = None) -> None:
        """Hold a peer's latest frame to send after any events, in place of what it held.

        The channel tells each peer's frames in the order it said them, so the latest told is
        the latest said.
        """
        key = (frame.peer, frame.artifact_id)
        watch = self._watches.get(frame.artifact_id)
        if watch is not None:
            if isinstance(frame, PeerLeft):
                watch.peers.discard(frame.peer)
            else:
                watch.peers.add(frame.peer)
        self._peers.pop(key, None)  # to the back: the oldest waiting goes first
        self._peers[key] = frame.model_dump_json() if text is None else text
        self._wake.set()

    def _put(self, frame: BaseModel) -> None:
        try:
            self._outbox.put_nowait(frame.model_dump_json())
        except asyncio.QueueFull:
            self._overflowed = True
        self._wake.set()

    def _crowded(self) -> bool:
        """Whether the outbox is more than half full: the client is falling behind."""
        size = self._outbox.maxsize
        return size > 0 and self._outbox.qsize() > size // 2

    async def _put_waiting(self, frame: BaseModel) -> None:
        """Queue a run's live frame, waiting for room rather than overflowing the outbox.

        A run's buffered frames arrive all at once when it is watched, more than the outbox may
        hold: the client is not slow for being sent them. Live frames stop short of the last
        ``1/OUTBOX_RESERVE`` of the outbox, which stays free for events, results and errors
        (``_put``), so a replay burst never makes those overflow. A client that leaves no room for
        :data:`LIVE_WAIT` seconds is slow after all, and is closed (4429). The channel sheds a
        watcher's oldest frames meanwhile.
        """
        text = frame.model_dump_json()
        size = self._outbox.maxsize
        limit = size - size // OUTBOX_RESERVE if size > 0 else float("inf")  # 0: unbounded
        try:
            async with asyncio.timeout(LIVE_WAIT):
                while self._outbox.qsize() >= limit:
                    self._room.clear()
                    await self._room.wait()
        except TimeoutError:
            self._overflowed = True
        else:
            self._outbox.put_nowait(text)
        self._wake.set()

    async def _write(self) -> None:
        """Send events first, then presence; presence never fills the outbox, nor closes it."""
        while True:
            if self._overflowed:
                await self._close(4429, "the client is not keeping up")
                return
            if not self._outbox.empty():
                await self._ws.send_text(self._outbox.get_nowait())
                self._room.set()
            elif self._peers:
                key = next(iter(self._peers))
                await self._ws.send_text(self._peers.pop(key))
            else:
                self._wake.clear()
                await self._wake.wait()

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


_PAGE = 100
"""How many envelopes of a thread a look for a run's latest start reads at a time."""


async def _started(
    workspace: Workspace, run_id: RunId, thread_id: ThreadId
) -> tuple[int, datetime | None]:
    """A running run's latest ``run_started``: its ``seq``, and when it was.

    It is read back from the thread's end; ``(0, None)`` where the thread's log doesn't hold it.
    """
    before: int | None = None
    while page := await workspace.read(threads={thread_id}, before_seq=before, last=_PAGE):
        for envelope in reversed(page):
            if isinstance(envelope.event, RunStarted) and envelope.event.run_id == run_id:
                return envelope.seq, envelope.ts
        before = page[0].seq
    return 0, None
