"""A scripted model, and the docplan server running for real on a free port.

No test calls a model API: the agent's model is a :class:`Script` that answers each request with
its next step.
"""

import asyncio
import json
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from docplan.app import create_app


def say(text: str) -> ModelResponse:
    """A step that replies with text."""
    return ModelResponse(parts=[TextPart(text)])


def call(tool: str, **args: Any) -> ModelResponse:
    """A step that calls one tool."""
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args)])


@dataclass
class Hold:
    """A step that waits, from the server's thread, until the test releases it."""

    then: ModelResponse
    entered: threading.Event = field(default_factory=threading.Event)
    released: threading.Event = field(default_factory=threading.Event)


type Reply = Callable[[list[ModelMessage]], ModelResponse]
"""A step that answers from the conversation so far, for runs that request concurrently."""

type Step = ModelResponse | Hold | Reply


class Script:
    """A model that answers each request with the next step. Tests append steps as they go."""

    def __init__(self, *steps: Step) -> None:
        self.steps = list(steps)

    @property
    def model(self) -> FunctionModel:
        return FunctionModel(self._respond, stream_function=self._stream)

    async def _next(self, messages: list[ModelMessage]) -> ModelResponse:
        step = self.steps.pop(0)
        if isinstance(step, Hold):
            step.entered.set()
            # The test releases it from its own thread. Waiting in slices keeps the wait
            # cancellable, so stopping the run ends it.
            while not await asyncio.to_thread(step.released.wait, 0.01):
                continue
            return step.then
        if isinstance(step, ModelResponse):
            return step
        return step(messages)

    async def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return await self._next(messages)

    async def _stream(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
        for index, part in enumerate((await self._next(messages)).parts):
            if isinstance(part, TextPart):
                yield part.content
            else:
                assert isinstance(part, ToolCallPart)
                args = json.dumps(part.args)
                yield {index: DeltaToolCall(name=part.tool_name, json_args=args)}


@pytest.fixture
def script() -> Script:
    return Script()


@pytest.fixture
def client(script: Script) -> Iterator[TestClient]:
    with TestClient(create_app(model=script.model), headers={"x-user": "alice"}) as client:
        yield client


@pytest.fixture
def server(script: Script) -> Iterator[str]:
    """Serve docplan on a free port in a background thread, and return its URL."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    config = uvicorn.Config(
        create_app(model=script.model), loop="asyncio", ws="websockets-sansio", log_level="warning"
    )
    served = uvicorn.Server(config)
    thread = threading.Thread(target=served.run, kwargs={"sockets": [listener]})
    thread.start()
    wait_for(lambda: served.started)
    yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    served.should_exit = True
    thread.join()


def wait_for(condition: Callable[[], object], timeout: float = 5.0) -> None:
    """Wait, polling, until ``condition()`` is truthy."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)
