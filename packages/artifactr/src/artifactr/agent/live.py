"""Live output: a run's token-level events, owned by whoever drives the run (ADR-0007).

Pass :func:`forward_live` as ``event_stream_handler`` to send a run's text, thinking and
tool-argument deltas, and application events, to a :class:`LiveChannel`. Nothing here touches
the durable log.
"""

import asyncio
import dataclasses
import json
from collections import OrderedDict, deque
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from pydantic_ai import (
    AgentStreamEvent,
    CustomEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    RunContext,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)

from artifactr.core import (
    AppLive,
    ArtifactId,
    Draft,
    LiveEvent,
    LiveFrame,
    PartEnded,
    PartStarted,
    RunId,
    TextDelta,
    ThinkingDelta,
    ToolArgsDelta,
)


@dataclasses.dataclass(kw_only=True, repr=False)
class ArtifactDraft(CustomEvent):
    """A snapshot of an artifact that a tool is still generating.

    Emit it from an application tool with ``await ctx.emit(ArtifactDraft(...))``; it reaches
    live channels as a ``draft`` frame and is never stored.
    """

    kind: str
    snapshot: dict[str, Any]
    artifact_id: ArtifactId | None = None


class LiveChannel(Protocol):
    """Where a run's live frames go."""

    async def send(self, frame: LiveFrame) -> None:
        """Deliver one frame. Delivery is best-effort."""
        ...


class NullChannel:
    """A channel that drops every frame, for headless runs."""

    async def send(self, frame: LiveFrame) -> None:
        """Drop the frame."""


class FanoutChannel:
    """An in-process channel that fans each run's frames out to its watchers.

    It keeps the frames of runs in progress, so a watcher that attaches mid-run first receives
    what the run has produced so far. Watchers that fall behind lose their oldest frames rather
    than slowing the run.

    Args:
        buffer: How many frames each run keeps, and each watcher may fall behind.
        remember_closed: How many ended runs to remember, so late watchers end at once.
    """

    def __init__(self, *, buffer: int = 1024, remember_closed: int = 10_000) -> None:
        self._buffer = buffer
        self._frames: dict[RunId, deque[LiveFrame]] = {}
        self._watchers: dict[RunId, set[asyncio.Queue[LiveFrame | None]]] = {}
        self._closed: OrderedDict[RunId, None] = OrderedDict()
        self._remember_closed = remember_closed

    async def send(self, frame: LiveFrame) -> None:
        """Keep a frame for the run, and deliver it to the run's current watchers."""
        if frame.run_id in self._closed:
            return
        self._frames.setdefault(frame.run_id, deque(maxlen=self._buffer)).append(frame)
        for queue in self._watchers.get(frame.run_id, ()):
            _offer(queue, frame)

    async def watch(self, run_id: RunId) -> AsyncIterator[LiveFrame]:
        """Yield the run's frames so far, then new ones until :meth:`close` is called for it.

        Watching a run that has already ended stops at once.
        """
        if run_id in self._closed:
            return
        queue: asyncio.Queue[LiveFrame | None] = asyncio.Queue(maxsize=self._buffer)
        for frame in self._frames.get(run_id, ()):
            _offer(queue, frame)
        watchers = self._watchers.setdefault(run_id, set())
        watchers.add(queue)
        try:
            while (frame := await queue.get()) is not None:
                yield frame
        finally:
            watchers.discard(queue)

    def close(self, run_id: RunId) -> None:
        """End every watcher of a run, and any that start watching it later."""
        self._closed[run_id] = None
        if len(self._closed) > self._remember_closed:
            self._closed.popitem(last=False)
        self._frames.pop(run_id, None)
        for queue in self._watchers.pop(run_id, ()):
            _offer(queue, None)


def _offer(queue: asyncio.Queue[LiveFrame | None], item: LiveFrame | None) -> None:
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(item)


EventStreamHandler = Callable[[RunContext[Any], AsyncIterable[AgentStreamEvent]], Awaitable[None]]


def forward_live(channel: LiveChannel) -> EventStreamHandler:
    """Return a pydantic-ai ``event_stream_handler`` that sends live frames to ``channel``.

    The run id comes from the run's ``Session``.
    """

    async def handle(ctx: RunContext[Any], events: AsyncIterable[AgentStreamEvent]) -> None:
        run_id: RunId = ctx.deps.run_id
        async for event in events:
            for live in to_live(event):
                await channel.send(LiveFrame(run_id=run_id, event=live))

    return handle


def to_live(event: AgentStreamEvent) -> list[LiveEvent]:
    """Translate one pydantic-ai stream event into live events (often none)."""
    match event:
        case PartStartEvent(index=index, part=TextPart(content=content)):
            return [PartStarted(part=index, part_kind="text"), *_text(index, content)]
        case PartStartEvent(index=index, part=ThinkingPart(content=content)):
            started = PartStarted(part=index, part_kind="thinking")
            return [started, *([ThinkingDelta(part=index, delta=content)] if content else [])]
        case PartStartEvent(index=index, part=ToolCallPart() as call):
            started = PartStarted(part=index, part_kind="tool_call", tool_name=call.tool_name)
            return [started, *_args(index, call.args_as_json_str() if call.args else None)]
        case PartDeltaEvent(index=index, delta=TextPartDelta(content_delta=delta)):
            return _text(index, delta)
        case PartDeltaEvent(index=index, delta=ThinkingPartDelta(content_delta=delta)):
            return [ThinkingDelta(part=index, delta=delta)] if delta else []
        case PartDeltaEvent(index=index, delta=ToolCallPartDelta(args_delta=delta)):
            return _args(index, delta)
        case PartEndEvent(index=index):
            return [PartEnded(part=index)]
        case ArtifactDraft(kind=kind, snapshot=snapshot, artifact_id=artifact_id):
            return [Draft(kind=kind, data=snapshot, artifact_id=artifact_id)]
        case CustomEvent(name=name):
            base = {f.name for f in dataclasses.fields(CustomEvent)}
            fields = dataclasses.asdict(event)
            data = {key: value for key, value in fields.items() if key not in base}
            return [AppLive(name=name, data=data)]
        case _:
            return []


def _text(index: int, text: str) -> list[LiveEvent]:
    return [TextDelta(part=index, delta=text)] if text else []


def _args(index: int, args: str | dict[str, Any] | None) -> list[LiveEvent]:
    if not args:
        return []
    delta = args if isinstance(args, str) else json.dumps(args)
    return [ToolArgsDelta(part=index, delta=delta)]
