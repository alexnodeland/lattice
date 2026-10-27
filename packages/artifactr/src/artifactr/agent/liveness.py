"""Liveness: a turn that waits on a model, or a tool, that sends nothing is failed, not left.

A model request that never answers, or a stream that stops mid-reply, would otherwise hold its
thread for as long as the client library waits, ten minutes through a gateway, while the thread
shows no progress. The runner wraps each turn's event stream in :func:`watched`: the first
event of each model request must arrive within :attr:`Liveness.first_output` seconds, each
later one within :attr:`Liveness.no_output`, and a tool call must return within
:attr:`Liveness.tool`. Otherwise the run fails with a typed reason, ``model_stalled`` or
``tool_stalled``, its request torn down and its usage so far recorded.

A model served locally is slower to its first token, so :func:`is_local_model` tells the two
apart by name, with the application's say as the last word, and the local limits apply.
"""

import asyncio
from collections.abc import AsyncIterable, Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Any, Final

from pydantic_ai import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    RunContext,
)

from artifactr.agent.capability import RunFailure

LOCAL_PREFIXES: Final = ("lm_studio/", "lmstudio/", "ollama/", "omlx/", "llamacpp/", "vllm/")
"""Name prefixes of models served on the operator's own hardware, as LiteLLM names them."""

LOCAL_ALIASES: Final = ("local", "local-", "local/", "local:")
"""Gateway aliases that name a local model: ``local`` itself, or one that starts with it."""

QUEUED: Final = 256
"""How many of a model's events wait for the handler before the model's stream is held back."""


def is_local_model(name: str, *, local: Collection[str] = (), hosted: Collection[str] = ()) -> bool:
    """Whether a model, by name, is served locally: slower to its first token than a host's.

    ``local`` and ``hosted`` are the application's own say, by exact name, which wins over the
    name's shape; ``hosted`` wins over ``local`` where both name it. Otherwise a name with a
    local provider's prefix (``ollama/``, ``lm_studio/``, ``omlx/``, ``llamacpp/``, ``vllm/``)
    or a ``local`` alias (``local``, ``local-*``, ``local/*``) is local, and any other name, an
    unknown one among them, is hosted.
    """
    if name in hosted:
        return False
    if name in local:
        return True
    lowered = name.lower()
    return lowered == LOCAL_ALIASES[0] or lowered.startswith(LOCAL_PREFIXES + LOCAL_ALIASES[1:])


@dataclass(frozen=True)
class Liveness:
    """How long a turn waits for a model, or a tool, that sends nothing, in seconds.

    Args:
        first_output: The most a hosted model's request may take to its first event.
        no_output: The most a hosted model may go between events, once it has started.
        local_first_output: The same, for a model served locally.
        local_no_output: The same, for a model served locally.
        tool: The most a tool call may take to return; ``None`` lets a tool take as long as it
            needs.
        local_models: Names of models to treat as local whatever their shape.
        hosted_models: Names of models to treat as hosted whatever their shape.
    """

    first_output: float = 120.0
    no_output: float = 120.0
    local_first_output: float = 300.0
    local_no_output: float = 300.0
    tool: float | None = 600.0
    local_models: frozenset[str] = frozenset()
    hosted_models: frozenset[str] = frozenset()

    def limits(self, model_name: str) -> tuple[float, float]:
        """The limits for a model, by name: to its first event, and between events."""
        if is_local_model(model_name, local=self.local_models, hosted=self.hosted_models):
            return self.local_first_output, self.local_no_output
        return self.first_output, self.no_output


class ModelStalled(RunFailure):
    """The model sent nothing for longer than the turn waits: the run fails, ``model_stalled``."""

    def __init__(self, model: str, seconds: float, *, first: bool) -> None:
        when = "didn't start answering" if first else "stopped answering"
        super().__init__(
            f"the model ({model}) {when} within {seconds:g} seconds", reason="model_stalled"
        )


class ToolStalled(RunFailure):
    """A tool call didn't return within the turn's wait: the run fails, ``tool_stalled``.

    ``tools`` names the calls still running as the wait ran out: the wait starts again at each
    event, so which of them stalled isn't known. A name called twice is named once. A call
    deferred to a person (``CallDeferred``, ``ApprovalRequired``) sends no result either, so
    beside a call that really hung it is named as still running too.
    """

    def __init__(self, tools: Collection[str], seconds: float) -> None:
        names = list(dict.fromkeys(tools))
        named = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        which, verb = ("tool", "is") if len(names) == 1 else ("tools", "are")
        super().__init__(
            f"the {which} {named} {verb} still running "
            f"and didn't return within {seconds:g} seconds",
            reason="tool_stalled",
        )


EventStreamHandler = Callable[[RunContext[Any], AsyncIterable[AgentStreamEvent]], Awaitable[None]]


def watched(handler: EventStreamHandler, liveness: Liveness) -> EventStreamHandler:
    """Return ``handler`` with the stream it is given timed by ``liveness``.

    pydantic-ai hands the handler one stream per model request, and one per round of tool
    calls. A model request's events are pulled in a task of their own, so a wait that runs out
    cancels that one pull, which tears the request down, and raises :class:`ModelStalled` to
    the run, which fails for that reason; ``handler`` sees exactly the events the model sent,
    in order. A tool round's call events arrive as the calls start; each call's result must
    follow within :attr:`Liveness.tool` seconds, or :class:`ToolStalled` is raised, and the
    calls still running are cancelled with the stream.
    """

    async def handle(ctx: RunContext[Any], events: AsyncIterable[AgentStreamEvent]) -> None:
        model = ctx.model.model_name
        first, between = liveness.limits(model)
        # Bounded, so a handler slower than the model holds the model's stream back a little
        # rather than the queue growing without end; the watchdog times the model, not the
        # handler, since a full queue is one that has events.
        queue: asyncio.Queue[AgentStreamEvent | None] = asyncio.Queue(maxsize=QUEUED)
        failed: list[BaseException] = []

        async def pull() -> None:
            # The stream's end is queued after its events, but not in a ``finally``: once the
            # handler has stopped, the puller is cancelled, and a put on a full queue then would
            # wait for a reader that is gone.
            try:
                async for event in events:
                    await queue.put(event)
            except Exception as error:
                failed.append(error)
            await queue.put(None)

        async def timed() -> AsyncIterable[AgentStreamEvent]:
            limit: float | None = first
            started = False  # whether the stream has sent anything yet
            calling: dict[str, str] = {}  # the tool calls under way, by call id: their names
            while True:
                try:
                    async with asyncio.timeout(limit):
                        event = await queue.get()
                except TimeoutError:
                    if calling:
                        raise ToolStalled(list(calling.values()), liveness.tool or 0) from None
                    raise ModelStalled(model, limit or 0, first=not started) from None
                started = True
                if event is None:
                    if failed:
                        raise failed[0]
                    return
                match event:
                    case FunctionToolCallEvent(part=part):
                        calling[part.tool_call_id] = part.tool_name
                    case FunctionToolResultEvent(tool_call_id=call_id):
                        calling.pop(call_id, None)
                    case _:
                        pass
                limit = liveness.tool if calling else between
                yield event

        puller = asyncio.create_task(pull())
        try:
            await handler(ctx, timed())
        finally:
            puller.cancel()
            await asyncio.gather(puller, return_exceptions=True)

    return handle
