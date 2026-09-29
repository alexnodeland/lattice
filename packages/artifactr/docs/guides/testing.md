# Testing your application

Everything in artifactr runs in one process without a network, so an application's tests can exercise the real workspace, the real agent capability and the real surfaces, with a scripted model in place of a model API. artifactr's own tests work this way; this page shows the patterns.

## Workspaces in memory

Give each test a fresh `InMemoryStorage`. It implements the full storage protocol, including transactions, subscriptions and leases, so nothing needs mocking:

```python
import pytest

from artifactr import InMemoryStorage, UserActor, Workspace, Workspaces
from artifactr.core import Thread


@pytest.fixture
async def ws() -> Workspace:
    workspaces = Workspaces(InMemoryStorage(), types=[Plan])
    return await workspaces.open("acme", "launch", actor=UserActor(id="u_alice", name="Alice"))


@pytest.fixture
async def thread(ws: Workspace) -> Thread:
    return await ws.create_thread("Launch")
```

Pass your own ids (`artifact_id="plan_1"`, `CreateThread(thread_id="thr_1")`) where a test needs to refer to them. To test lease expiry, give the storage a clock you control: `InMemoryStorage(clock=lambda: now)`.

The examples on this page use [pytest-asyncio](https://pytest-asyncio.readthedocs.io) with `asyncio_mode = "auto"`, so async tests and fixtures need no decorators.

## Assert on the log

The log records everything that happened, in order and attributed, which makes it the natural thing to assert on:

```python
log = await ws.read()
assert [envelope.event.type for envelope in log][-2:] == ["message_posted", "run_ended"]
assert log[-1].actor.kind == "agent"
```

Reads such as `ws.proposals()`, `ws.revisions(artifact_id)` and `ws.run(run_id)` check the resulting state.

## A model that needs no API

pydantic-ai's [`TestModel`](https://ai.pydantic.dev/testing/) answers without calling anything. By default it calls every tool with generated arguments, which rarely makes sense for artifact tools; `call_tools=[]` makes it only reply. Swap it into your application's agent with `agent.override`:

```python
from pydantic_ai.models.test import TestModel


async def test_the_agent_replies(ws: Workspace, thread: Thread) -> None:
    with agent.override(model=TestModel(call_tools=[], custom_output_text="On it.")):
        sent = await runner.send(ws, thread.id, "Plan the launch.")
        assert sent.run is not None
        await sent.run.wait()

    log = await ws.read()
    assert [envelope.event.type for envelope in log][-2:] == ["message_posted", "run_ended"]
```

The override applies to runs the `Runner` starts inside the `with` block, since they inherit its context. Constructing an agent from a model name such as `"anthropic:claude-sonnet-5-5"` needs that provider's API key unless you pass `defer_model_check=True`, as the [reference implementation](../reference-implementation.md) does, so tests can import the agent without a key.

## Scripting the model

To test what the agent does (which tools it calls, what it proposes, how it reacts to a rejection), script the model's responses. pydantic-ai's `FunctionModel` answers each request with a function of yours, but the `Runner` streams every run, so the model needs a stream function too. `artifactr.agent.function_model` builds both from one function, sync or async, that returns a `ModelResponse`: the stream carries its text, its thinking and its tool calls.

A `Script` that answers each request with the next response is then a few lines, as in artifactr's own [`tests/agent/conftest.py`](https://github.com/alexnodeland/artifactr/blob/main/tests/agent/conftest.py):

```python
from typing import Any

from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from artifactr.agent import function_model


class Script:
    """A model that answers each request with the next scripted response."""

    def __init__(self, *responses: ModelResponse) -> None:
        self.responses = list(responses)
        self.requests: list[list[ModelMessage]] = []  # what the model was sent, per request

    @property
    def model(self) -> FunctionModel:
        return function_model(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(list(messages))
        return self.responses.pop(0)


def say(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def call(tool: str, call_id: str = "call_1", **args: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool, args, tool_call_id=call_id)])
```

Each model request takes the next response: typically a tool call, then a reply once the tool has returned. The test then checks both what the agent did and what it was told:

```python
from pydantic_ai import ModelRequest


async def test_the_agent_proposes_tasks(ws: Workspace, thread: Thread) -> None:
    await ws.create(Plan(goal="Ship v1"), artifact_id="plan_1")
    script = Script(
        call("add_task", plan_id="plan_1", title="Write the changelog"),
        say("I proposed a task."),
    )
    with agent.override(model=script.model):
        sent = await runner.send(ws, thread.id, "What is missing?")
        assert sent.run is not None
        await sent.run.wait()

    [proposal] = await ws.proposals()
    assert proposal.proposed_by.kind == "agent"

    last = script.requests[-1][-1]
    assert isinstance(last, ModelRequest)
    assert "Kinds of artifact you can create: plan." in (last.instructions or "")
```

`script.requests` holds every message list the model received, so a test can check the instructions, the change notes (user-prompt parts wrapped in `<workspace-changes>`) and the tool results the agent saw. artifactr's own agent tests, in [`tests/agent/`](https://github.com/alexnodeland/artifactr/tree/main/tests/agent), use this to cover steering, pauses and conflicts.

To hold a run open while a test does something else (posting a steering message, stopping the run, watching its live output), give it an application tool that waits on an `asyncio.Event` the test controls, as the `Gate` in the same `conftest.py` does.

## The web surfaces

FastAPI's `TestClient` drives the router in-process, over REST and WebSocket:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_a_client_replays_the_log() -> None:
    app = FastAPI()
    app.include_router(
        artifactr_router(workspaces, runner, resolve_actor=resolve_actor), prefix="/v1"
    )
    with TestClient(app) as client:
        frame = {
            "type": "command",
            "command_id": "c1",
            "command": {"type": "create_thread", "thread_id": "thr_1"},
        }
        assert client.post("/v1/workspaces/launch/commands", json=frame).json()["ok"]

        with client.websocket_connect(
            "/v1/workspaces/launch/stream", subprotocols=["artifactr.v1"]
        ) as socket:
            socket.send_json({"type": "hello", "protocol": "artifactr.v1", "resume_after_seq": 0})
            assert socket.receive_json()["type"] == "welcome"
            assert socket.receive_json()["event"]["type"] == "thread_created"
            assert socket.receive_json() == {"type": "replay_complete", "up_to_seq": 1}
```

A `resolve_actor` that reads a test header, such as `x-user`, lets one test act as several people. The MCP server is tested with the MCP SDK's in-process client, `async with mcp.Client(server.server) as client:`, as in [External agents over MCP](mcp.md#trying-it).

## Tips

- pydantic-ai may print an observability banner when an agent is built. artifactr's test suite sets `PYDANTIC_AI_NO_BANNER=1` in its `conftest.py` to keep test output clean.
- Tests that start runs should wait for them (`await sent.run.wait()`) before the test ends, so no task outlives its event loop.
- The [reference implementation's tests](https://github.com/alexnodeland/artifactr/tree/main/examples/docplan/tests) go one step further: they start the real server with uvicorn on a free port and drive it with the real terminal client, still with a scripted model.
