"""The surfaces attribute their spans, and the WebSocket stream is traced and counted."""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi.testclient import TestClient
from mcp.server.mcpserver import Context
from opentelemetry.trace import Tracer

from artifactr.core import ExternalAgentActor, TenantId
from artifactr.mcp import ArtifactrMcp
from artifactr.telemetry.attributes import (
    ACTOR_KIND,
    CLOSE_CODE,
    TENANT_ID,
    USER_ID,
    WORKSPACE_ID,
)
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.agent.conftest import Gate, Script, make_agent, make_runner
from tests.fastapi.conftest import build, command, hello, wait_for
from tests.telemetry.conftest import Recorder, attributes

STREAM = "/v1/workspaces/w1/stream"

type Scope = MutableMapping[str, Any]
type Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
type Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
type App = Callable[[Scope, Receive, Send], Awaitable[None]]


class Traced:
    """Middleware that traces each HTTP request, as FastAPI's instrumentation would."""

    def __init__(self, app: App, tracer: Tracer) -> None:
        self.app = app
        self.tracer = tracer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with self.tracer.start_as_current_span("POST"):
            await self.app(scope, receive, send)


def test_a_rest_request_is_attributed(recorder: Recorder) -> None:
    app, _ = build(Script())
    app.add_middleware(Traced, tracer=recorder.tracer_provider.get_tracer("http"))
    with TestClient(app) as client:
        response = client.post(
            "/v1/workspaces/w1/commands",
            json=command("c1", type="create_thread"),
            headers={"x-tenant": "t1", "x-user": "bob"},
        )
    assert response.status_code == 200
    assert attributes(recorder.span("POST")) == {
        TENANT_ID: "t1",
        WORKSPACE_ID: "w1",
        ACTOR_KIND: "user",
        USER_ID: "bob",
    }


def test_a_websocket_connection_is_traced_and_counted(recorder: Recorder) -> None:
    app, _ = build(Script(), **recorder.providers)
    with (
        TestClient(app) as client,
        client.websocket_connect(STREAM, headers={"x-tenant": "t1"}) as ws,
    ):
        ws.send_json(hello())
        assert ws.receive_json()["type"] == "welcome"
        assert ws.receive_json()["type"] == "replay_complete"
        wait_for(lambda: recorder.total("artifactr.stream.connections") == 1)
        ws.close(1000)
        wait_for(lambda: bool(recorder.spans("artifactr.stream")))
    assert attributes(recorder.span("artifactr.stream")) == {
        TENANT_ID: "t1",
        WORKSPACE_ID: "w1",
        ACTOR_KIND: "user",
        USER_ID: "alice",
        CLOSE_CODE: "1000",
    }
    assert recorder.points("artifactr.stream.connections") == [
        ({TENANT_ID: "t1", WORKSPACE_ID: "w1"}, 0)
    ]
    where = {CLOSE_CODE: "1000", TENANT_ID: "t1"}
    assert recorder.total("artifactr.stream.disconnects", where) == 1


def test_a_refused_connection_is_counted_by_its_close_code(recorder: Recorder) -> None:
    app, _ = build(Script(), **recorder.providers)
    with (
        TestClient(app) as client,
        client.websocket_connect(STREAM, headers={"x-token": "bad"}) as ws,
    ):
        assert ws.receive()["code"] == 4401
        wait_for(lambda: bool(recorder.spans("artifactr.stream")))
    assert attributes(recorder.span("artifactr.stream"))[CLOSE_CODE] == "4401"
    assert recorder.points("artifactr.stream.connections") == []
    assert recorder.points("artifactr.stream.disconnects") == [
        ({WORKSPACE_ID: "w1", CLOSE_CODE: "4401"}, 1)
    ]


async def test_mcp_requests_are_attributed_on_the_sdks_spans(recorder: Recorder) -> None:
    client = ExternalAgentActor(client_id="claude-code")

    async def resolve(ctx: Context) -> tuple[TenantId, ExternalAgentActor]:
        return "t1", client

    runner = make_runner(make_agent(Script()), Gate())
    mcp = ArtifactrMcp(Workspaces(InMemoryStorage()), runner, resolve=resolve)
    tracer = recorder.tracer_provider.get_tracer("mcp-python-sdk")
    try:
        with tracer.start_as_current_span("tools/call list_artifacts"):
            await mcp._open(Context(), "w1")
    finally:
        await mcp.aclose()
    assert attributes(recorder.span("tools/call list_artifacts")) == {
        TENANT_ID: "t1",
        WORKSPACE_ID: "w1",
        ACTOR_KIND: "external_agent",
    }
