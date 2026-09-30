"""A scripted model and fixtures for agent tests: no test calls a model API."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
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
    UserPromptPart,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models.function import AgentInfo, FunctionModel

from artifactr.agent import ArtifactWorkspace, RunHandle, Runner, Sent, Session, function_model
from artifactr.core import Envelope, Run, RunStatus, Thread, ThreadId, UserActor
from artifactr.workspace import HistoryChunk, InMemoryStorage, Scope, Workspace, Workspaces
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
        """Every user-prompt text in a request's messages, each of a prompt's several apart."""
        return [
            str(text)
            for message in self.requests[request]
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart)
            for text in ([part.content] if isinstance(part.content, str) else part.content)
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

    ``held`` holds every release of a claim until the gate is released. The others hold the
    next call of their kind, once: a claim, a read of a cursor, a read of the log's head, a
    read of a thread's paused runs (as a claimant plans), a read of a thread's history (as a
    turn starts), a subscription (as a run's watcher starts), and the save of a thread's
    taken position, held once it is saved, as SQL storage finishes a save and only then
    raises a cancellation. It counts claims, and refuses one past ``MAX_CLAIMS``, so a
    claimant that never stops fails its test rather than hanging it.
    """

    MAX_CLAIMS = 50

    def __init__(self) -> None:
        super().__init__()
        self.held: Gate | None = None
        self.held_claim: Gate | None = None
        self.held_read: Gate | None = None
        self.held_runs: Gate | None = None
        self.held_history: Gate | None = None
        self.held_subscribe: Gate | None = None
        self.held_head: Gate | None = None
        self.held_taken: Gate | None = None
        self.claims = 0

    async def release_lease(self, scope: Scope, key: str, holder: str) -> None:
        if self.held is not None:
            await self.held.wait()
        await super().release_lease(scope, key, holder)

    async def acquire_lease(self, scope: Scope, key: str, holder: str, ttl: timedelta) -> bool:
        self.claims += 1
        if self.claims > self.MAX_CLAIMS:
            raise RuntimeError(f"claimed {self.claims} times")
        if (gate := self.held_claim) is not None:
            self.held_claim = None
            await gate.wait()
        return await super().acquire_lease(scope, key, holder, ttl)

    async def cursor(self, scope: Scope, name: str) -> int:
        if (gate := self.held_read) is not None:
            self.held_read = None
            await gate.wait()
        return await super().cursor(scope, name)

    async def head_seq(self, scope: Scope) -> int:
        if (gate := self.held_head) is not None:
            self.held_head = None
            await gate.wait()
        return await super().head_seq(scope)

    async def save_cursor(self, scope: Scope, name: str, seq: int) -> None:
        await super().save_cursor(scope, name, seq)
        if name.endswith("/taken") and (gate := self.held_taken) is not None:
            self.held_taken = None
            await gate.wait()

    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        if status == "paused" and (gate := self.held_runs) is not None:
            self.held_runs = None
            await gate.wait()
        return await super().runs(scope, thread_id=thread_id, status=status)

    async def history(self, scope: Scope, thread_id: ThreadId) -> Sequence[HistoryChunk]:
        if (gate := self.held_history) is not None:
            self.held_history = None
            await gate.wait()
        return await super().history(scope, thread_id)

    async def subscribe(self, scope: Scope, *, after_seq: int = 0) -> AsyncGenerator[Envelope]:
        if (gate := self.held_subscribe) is not None:
            self.held_subscribe = None
            await gate.wait()
        async for envelope in super().subscribe(scope, after_seq=after_seq):
            yield envelope


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


async def settled(thread_id: str, *runners: Runner[Gate]) -> None:
    """Wait until no runner has a hand-over pending or a run in the thread."""
    while True:
        for runner in runners:
            await runner.drain()
        runs = [handle.task for runner in runners if (handle := runner.running(thread_id))]
        if not runs:
            return
        await asyncio.gather(*runs, return_exceptions=True)


def types(envelopes: Sequence[Envelope]) -> list[str]:
    return [envelope.event.type for envelope in envelopes]


def started(sent: Sent) -> RunHandle:
    """The run a message or answer started or resumed."""
    assert sent.run is not None, "expected the message to start or resume a run"
    return sent.run


def event_as[E](envelope: Envelope, event_type: type[E]) -> E:
    assert isinstance(envelope.event, event_type), f"{envelope.event.type} is not {event_type}"
    return envelope.event
