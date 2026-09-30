"""A scripted model and fixtures for agent tests: no test calls a model API."""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import timedelta
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    FunctionToolset,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RunContext,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models.function import AgentInfo, FunctionModel

from artifactr.agent import ArtifactWorkspace, RunHandle, Runner, Sent, Session, function_model
from artifactr.core import Envelope, Thread, UserActor
from artifactr.workspace import InMemoryStorage, Scope, Workspace, Workspaces
from tests.artifact_types import Checklist, Note

ALICE = UserActor(id="alice", name="Alice")

Step = ModelResponse | Callable[[list[ModelMessage]], ModelResponse]


def say(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def call(tool: str, call_id: str = "call_1", **args: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args, tool_call_id=call_id)])


class Script:
    """A model that answers each request with the next scripted step, recording requests."""

    def __init__(self, *steps: Step) -> None:
        self.steps = list(steps)
        self.requests: list[list[ModelMessage]] = []

    @property
    def model(self) -> FunctionModel:
        return function_model(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(list(messages))
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step

    def instructions(self, request: int) -> str:
        last = self.requests[request][-1]
        assert isinstance(last, ModelRequest)
        return last.instructions or ""

    def tool_returns(self, request: int) -> list[str]:
        """The tool results sent to the model in a request."""
        last = self.requests[request][-1]
        assert isinstance(last, ModelRequest)
        return [str(p.content) for p in last.parts if isinstance(p, ToolReturnPart)]

    def prompt_texts(self, request: int) -> list[str]:
        """Every user-prompt text in a request's messages."""
        return [
            str(part.content)
            for message in self.requests[request]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if part.part_kind == "user-prompt"
        ]

    def conversation(self) -> list[str]:
        """The thread's messages as the model last saw them, in order: prompts and steering."""
        return self.prompt_texts(len(self.requests) - 1)

    def answers(self) -> list[str]:
        """The tool results the model last saw, in order: its questions' answers among them."""
        return [
            str(part.content)
            for message in self.requests[-1]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if part.part_kind == "tool-return"
        ]


class Gate:
    """Lets a test hold a tool call open until it chooses to release it."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def wait(self) -> None:
        self.entered.set()
        await self.release.wait()


class HeldStorage(InMemoryStorage):
    """Storage that holds calls where a test asks it to, each at a :class:`Gate`.

    ``held`` holds every release of a claim until the gate is released. ``held_claim`` and
    ``held_read`` hold the next claim, or the next read of a cursor, once.
    """

    def __init__(self) -> None:
        super().__init__()
        self.held: Gate | None = None
        self.held_claim: Gate | None = None
        self.held_read: Gate | None = None

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        if self.held is not None:
            await self.held.wait()
        await super().release_lease(scope, key, holder)

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        if (gate := self.held_claim) is not None:
            self.held_claim = None
            await gate.wait()
        return await super().acquire_lease(scope, key, holder, ttl)

    async def cursor(self, scope: Scope, name: str) -> int:
        if (gate := self.held_read) is not None:
            self.held_read = None
            await gate.wait()
        return await super().cursor(scope, name)


async def settle() -> None:
    """Let the tasks that are ready run, such as a run's watcher delivering what was posted."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture
def gate() -> Gate:
    return Gate()


@pytest.fixture
def app_tools(gate: Gate) -> FunctionToolset[Session[Gate]]:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool
    async def hold(ctx: RunContext[Session[Gate]]) -> str:
        """Wait until the test releases the gate."""
        await ctx.deps.app.wait()
        return "released"

    return tools


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
async def ws(storage: InMemoryStorage) -> Workspace:
    return await Workspaces(storage).open("tenant", "ws", actor=ALICE)


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    return await ws.create_thread("Launch")


def make_agent(
    script: Script,
    *,
    tools: Sequence[FunctionToolset[Session[Gate]]] = (),
    ask: bool = False,
    notices: bool = False,
    output_type: Any = str,
    capabilities: Sequence[AbstractCapability[Session[Gate]]] = (),
) -> Agent[Session[Gate], Any]:
    return Agent(
        script.model,
        deps_type=Session[Gate],
        output_type=output_type,
        toolsets=list(tools),
        capabilities=[
            ArtifactWorkspace(types=[Note, Checklist], ask=ask, notices=notices),
            *capabilities,
        ],
    )


def make_runner(agent: Agent[Session[Gate], Any], gate: Gate) -> Runner[Gate]:
    return Runner(agent, app=gate)


type MakeRunner = Callable[..., Runner[Gate]]
"""Makes a runner of an agent, with the runner's other arguments."""


@pytest.fixture
async def runners(gate: Gate) -> AsyncIterator[MakeRunner]:
    """Make runners that are closed as the test ends, so one that is stuck fails the test."""
    made: list[Runner[Gate]] = []

    def make(agent: Agent[Session[Gate], Any], **options: Any) -> Runner[Gate]:
        runner = Runner(agent, app=gate, **options)
        made.append(runner)
        return runner

    yield make
    for runner in made:
        await runner.aclose()


async def settled(runner: Runner[Gate], thread_id: str) -> None:
    """Wait until the runner has nothing more to do in a thread: every hand-over and every run."""
    while True:
        await runner.drain()
        handle = runner.running(thread_id)
        if handle is None:
            return
        await asyncio.gather(handle.task, return_exceptions=True)


def types(envelopes: Sequence[Envelope]) -> list[str]:
    return [envelope.event.type for envelope in envelopes]


def started(sent: Sent) -> RunHandle:
    """The run a message or answer started or resumed."""
    assert sent.run is not None, "expected the message to start or resume a run"
    return sent.run


def event_as[E](envelope: Envelope, event_type: type[E]) -> E:
    assert isinstance(envelope.event, event_type), f"{envelope.event.type} is not {event_type}"
    return envelope.event
