"""The permission matrix (lattice RFC-0001, ADR-0056): every way in asks ``authorize``.

Every public ``Workspace`` and ``Workspaces`` method is listed with what it asks for, and every
REST route, WebSocket command, and MCP tool and resource with the actions its caller is asked
for, which are those of the methods it calls. Each is called with a hook that records what it
is asked. A method or surface missing from the tables fails, as does one that asks for an
action outside :data:`~artifactr.workspace.ACTIONS`, or one that asks for nothing. A surface
that is open on purpose is listed with its reason, and asks nothing.
"""

import asyncio
import inspect
import time
import typing
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient
from mcp import Client
from mcp.types import TextContent
from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo
from starlette.requests import HTTPConnection

from artifactr.agent import ArtifactWorkspace, Runner, Session, function_model
from artifactr.connect import RUN_CODE
from artifactr.core import (
    Actor,
    AgentActor,
    Command,
    CreateThread,
    ExternalAgentActor,
    ProposeChange,
    RunStarted,
    SystemActor,
    TenantId,
    UserActor,
    WorkspaceId,
)
from artifactr.fastapi import artifactr_router
from artifactr.files.native import CREATE_NATIVE_FILE
from artifactr.mcp import ArtifactrMcp, artifact_uri
from artifactr.workspace import ACTIONS, Access, InMemoryStorage, Workspace, Workspaces
from tests.artifact_types import Note
from tests.fastapi.conftest import closing

TENANT, WORKSPACE = "tenant", "w1"
TENANT_WIDE = "artifactr:read_workspaces"
"""The one action asked with no workspace."""
ALICE = UserActor(id="alice", name="Alice")
CLIENT = ExternalAgentActor(client_id="claude", on_behalf_of=ALICE)
THREAD, RUN, ARTIFACT, PROPOSAL = "thr_1", "run_1", "n1", "prp_1"


class Recorder:
    """An ``authorize`` hook that allows everything and records what it is asked, by whom."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []
        self.refused: frozenset[str] = frozenset()

    async def __call__(
        self, tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        assert tenant_id == TENANT
        assert workspace_id == (None if access.action == TENANT_WIDE else WORKSPACE)
        self.asked.append((actor.participant, access.action))
        return access.action not in self.refused

    def by(self, actor: Actor) -> list[str]:
        """What ``actor`` was asked for, in order, and forget it all."""
        asked = [action for participant, action in self.asked if participant == actor.participant]
        self.asked.clear()
        return asked


def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("ok")])


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def workspaces(recorder: Recorder) -> Workspaces:
    return Workspaces(InMemoryStorage(), types=[Note], authorize=recorder)


@pytest.fixture
def runner() -> Runner[None]:
    agent: Agent[Session[None], Any] = Agent(
        function_model(_respond),
        deps_type=Session[None],
        capabilities=[ArtifactWorkspace(types=[Note])],
    )
    return Runner(agent, app=None)


async def _seed(workspaces: Workspaces, recorder: Recorder) -> Workspace:
    """A workspace with a thread, an artifact, a proposal and a run; then nothing asked."""
    ws = await workspaces.open(TENANT, WORKSPACE, actor=ALICE)
    await ws.commit(CreateThread(thread_id=THREAD, title="Launch"))
    await ws.create(Note(text="Friday"), artifact_id=ARTIFACT)
    edit = (await ws.get(Note, ARTIFACT)).edit_text("Friday", "Monday")
    agent = ws.as_actor(AgentActor(thread_id=THREAD, run_id=RUN))
    await agent.commit(ProposeChange(proposal_id=PROPOSAL, change=edit))
    await agent.record(RunStarted(run_id=RUN, thread_id=THREAD))
    recorder.asked.clear()
    return ws


# ─── every public Workspace method ───────────────────────────────────────────

type Call = Callable[[Workspace], Awaitable[object]]


async def _subscribe(ws: Workspace) -> None:
    await anext(aiter(ws.subscribe()))


async def _claim(ws: Workspace) -> None:
    async with ws.claim_thread(THREAD, holder="h", ttl=timedelta(seconds=5)):
        pass


METHODS: dict[str, tuple[Call, str]] = {
    "commit": (lambda ws: ws.commit(CreateThread()), "artifactr:create_thread"),
    "record": (
        lambda ws: ws.as_actor(AgentActor(thread_id=THREAD, run_id="run_2")).record(
            RunStarted(run_id="run_2", thread_id=THREAD)
        ),
        "artifactr:record",
    ),
    "create": (lambda ws: ws.create(Note()), "artifactr:create_artifact"),
    "create_thread": (lambda ws: ws.create_thread(), "artifactr:create_thread"),
    "post_message": (lambda ws: ws.post_message(THREAD, "hi"), "artifactr:post_message"),
    "get": (lambda ws: ws.get(Note, ARTIFACT), "artifactr:read_artifacts"),
    "artifact": (lambda ws: ws.artifact(ARTIFACT), "artifactr:read_artifacts"),
    "artifacts": (lambda ws: ws.artifacts(), "artifactr:read_artifacts"),
    "revisions": (lambda ws: ws.revisions(ARTIFACT), "artifactr:read_artifacts"),
    "thread": (lambda ws: ws.thread(THREAD), "artifactr:read_threads"),
    "threads": (lambda ws: ws.threads(), "artifactr:read_threads"),
    "proposal": (lambda ws: ws.proposal(PROPOSAL), "artifactr:read_proposals"),
    "proposals": (lambda ws: ws.proposals(), "artifactr:read_proposals"),
    "run": (lambda ws: ws.run(RUN), "artifactr:read_runs"),
    "runs": (lambda ws: ws.runs(), "artifactr:read_runs"),
    "history": (lambda ws: ws.history(THREAD), "artifactr:read_history"),
    "head_seq": (lambda ws: ws.head_seq(), "artifactr:read_events"),
    "read": (lambda ws: ws.read(), "artifactr:read_events"),
    "subscribe": (_subscribe, "artifactr:read_events"),
    "change_notes": (lambda ws: ws.change_notes(after_seq=0), "artifactr:read_events"),
    "cursor": (lambda ws: ws.cursor("c"), "artifactr:read_cursors"),
    "save_cursor": (lambda ws: ws.save_cursor("c", 1), "artifactr:save_cursor"),
    "claim_thread": (_claim, "artifactr:claim_thread"),
    "lease_artifact": (
        lambda ws: ws.lease_artifact(ARTIFACT, holder="h", ttl=timedelta(seconds=5)),
        "artifactr:edit_artifact",
    ),
    "artifact_lease": (lambda ws: ws.artifact_lease(ARTIFACT), "artifactr:read_artifacts"),
    "release_artifact": (
        lambda ws: ws.release_artifact(ARTIFACT, holder="h"),
        "artifactr:edit_artifact",
    ),
}
"""Each public ``Workspace`` method, a call of it, and the one action it asks for."""

OPEN_METHODS = {
    "as_actor": "derives a handle for another actor, whose methods ask as that actor",
    "check": "is the asking itself: what every other method calls",
    "hidden": "is what every read leaves out, which a surface asks of the handle it was given",
}
"""Public ``Workspace`` methods that ask for no action of their own, and why."""


WORKSPACES_METHODS: dict[str, tuple[Callable[[Workspaces], Awaitable[object]], list[str]]] = {
    "open": (lambda w: w.open(TENANT, WORKSPACE, actor=ALICE), ["artifactr:open"]),
    "list": (lambda w: w.list(TENANT, actor=ALICE), [TENANT_WIDE, "artifactr:open"]),
}
"""Each public ``Workspaces`` method, a call of it, and what it asks for: listing asks to open
each workspace it finds, here the one seeded."""


def _public_methods(cls: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_") and inspect.isfunction(member)
    }


TWICE_METHODS = {
    "watch": (
        lambda ws: ws.watch(ARTIFACT),
        ["artifactr:read_artifacts", "artifactr:edit_artifact"],
    ),
}
"""Public ``Workspace`` methods that ask two actions: a watch reads, then asks whether it may
edit, to say which the watcher may do."""


def test_every_public_method_is_listed() -> None:
    assert _public_methods(Workspace) == set(METHODS) | set(OPEN_METHODS) | set(TWICE_METHODS)
    assert _public_methods(Workspaces) == set(WORKSPACES_METHODS)


@pytest.mark.parametrize("method", sorted(METHODS))
async def test_each_method_asks_for_its_action_once(
    workspaces: Workspaces, recorder: Recorder, method: str
) -> None:
    ws = await _seed(workspaces, recorder)
    call, action = METHODS[method]
    await call(ws)
    assert [action for _, action in recorder.asked] == [action]
    assert action in ACTIONS


@pytest.mark.parametrize("method", sorted(TWICE_METHODS))
async def test_each_method_that_asks_twice_asks_its_actions_in_order(
    workspaces: Workspaces, recorder: Recorder, method: str
) -> None:
    ws = await _seed(workspaces, recorder)
    call, actions = TWICE_METHODS[method]
    await call(ws)
    assert [action for _, action in recorder.asked] == actions


@pytest.mark.parametrize("method", sorted(WORKSPACES_METHODS))
async def test_each_workspaces_method_asks_for_its_actions(
    workspaces: Workspaces, recorder: Recorder, method: str
) -> None:
    await _seed(workspaces, recorder)
    call, actions = WORKSPACES_METHODS[method]
    await call(workspaces)
    assert recorder.by(ALICE) == actions


def _command_types() -> set[str]:
    [union, _] = typing.get_args(Command)
    return {model.model_fields["type"].default for model in typing.get_args(union)}


# ─── every WebSocket command, and every REST route ───────────────────────────

FRAMES: dict[str, tuple[dict[str, Any], list[str]]] = {
    "create_artifact": ({"kind": "note", "data": {}}, ["artifactr:create_artifact"]),
    "edit_artifact": (
        {
            "artifact_id": ARTIFACT,
            "base_version": 1,
            "patch": {"kind": "json_patch", "ops": [{"op": "add", "path": "/text", "value": ""}]},
        },
        ["artifactr:edit_artifact"],
    ),
    "archive_artifact": (
        {"artifact_id": ARTIFACT, "base_version": 9},
        ["artifactr:archive_artifact"],
    ),
    "propose_change": (
        {"change": {"type": "create_artifact", "kind": "note", "data": {}}},
        ["artifactr:propose_change"],
    ),
    "respond_to_proposal": (
        {"proposal_id": PROPOSAL, "decision": "reject"},
        ["artifactr:respond_to_proposal"] * 2,  # of the workspace, then of the artifact
    ),
    "create_thread": ({}, ["artifactr:create_thread"]),
    "post_message": ({"thread_id": THREAD, "content": "hi"}, ["artifactr:post_message"]),
    "set_focus": ({"thread_id": THREAD, "artifact_ids": []}, ["artifactr:set_focus"]),
    "set_thread_mode": ({"thread_id": THREAD, "mode": "suggest"}, ["artifactr:set_thread_mode"]),
    "answer_deferred": (
        {"run_id": RUN, "tool_call_id": "q1", "answer": "Monday"},
        ["artifactr:answer_deferred"] * 2,  # of the workspace, then of the run's thread
    ),
    "give_feedback": (
        {"feedback_type": "helpfulness", "target": {"kind": "thread", "thread_id": THREAD}},
        ["artifactr:give_feedback"],
    ),
    "stop_run": ({"run_id": RUN}, ["artifactr:read_runs", "artifactr:stop_run"]),
    "watch_run": ({"run_id": RUN}, ["artifactr:read_runs"]),
}
"""Each command a client may send, fields for it, and what its sender is asked for.

The runner carries a message out: the sender is asked to post it, and the runner's own work,
such as claiming the thread and running the agent, is asked as the runner and the agent.
A command whose rules then refuse it was still asked about first.
"""

CONNECT = [
    "artifactr:open",
    "artifactr:read_events",
    "artifactr:read_runs",
    "artifactr:read_events",
    "artifactr:read_events",
    "artifactr:read_events",
]
"""What a WebSocket connection is asked for as it opens: its workspace, the log's head and the
runs in progress (welcome), then the log it replays, here in one page, the log it follows, and,
for the run in progress, its thread's log, back to where the run's turn started."""

ROUTES: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("POST", "/workspaces/{workspace_id}/commands"): ("", ["artifactr:create_thread"]),
    ("GET", "/workspaces/{workspace_id}/artifacts"): ("", ["artifactr:read_artifacts"]),
    ("GET", "/workspaces/{workspace_id}/artifacts/{artifact_id}"): (
        ARTIFACT,
        ["artifactr:read_artifacts"],
    ),
    ("GET", "/workspaces/{workspace_id}/artifacts/{artifact_id}/revisions"): (
        ARTIFACT,
        ["artifactr:read_artifacts"],
    ),
    ("GET", "/workspaces/{workspace_id}/events"): ("", ["artifactr:read_events"]),
    ("GET", "/workspaces/{workspace_id}/threads"): ("", ["artifactr:read_threads"]),
    ("GET", "/workspaces/{workspace_id}/threads/{thread_id}"): (
        THREAD,
        ["artifactr:read_threads"],
    ),
    ("GET", "/workspaces/{workspace_id}/proposals"): ("", ["artifactr:read_proposals"]),
    ("GET", "/workspaces/{workspace_id}/runs/{run_id}"): (RUN, ["artifactr:read_runs"]),
    ("WEBSOCKET", "/workspaces/{workspace_id}/stream"): ("", CONNECT[1:]),
}
"""Each route, the id its path names last, if any, and what its caller is asked for after
``artifactr:open``."""

TENANT_ROUTES: dict[tuple[str, str], list[str]] = {
    ("GET", "/workspaces"): [TENANT_WIDE, "artifactr:open"],
}
"""Each route that names no workspace, and what its caller is asked for."""


async def _resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    return TENANT, ALICE


@pytest.fixture
def router(workspaces: Workspaces, runner: Runner[None]) -> APIRouter:
    return artifactr_router(workspaces, runner, resolve_actor=_resolve_actor)


@pytest.fixture
def client(
    workspaces: Workspaces, recorder: Recorder, runner: Runner[None], router: APIRouter
) -> Iterator[TestClient]:
    app = closing(runner)
    app.include_router(router)
    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(_seed, workspaces, recorder)
        yield client


def _routes(router: APIRouter) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in router.routes:
        if isinstance(route, APIRoute):
            found |= {(method, route.path) for method in route.methods or ()}
        else:
            assert isinstance(route, APIWebSocketRoute)
            found.add(("WEBSOCKET", route.path))
    return found


def _wait_for(check: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not check():
        assert time.monotonic() < deadline, "timed out waiting"
        time.sleep(0.01)


def test_every_route_asks_for_the_actions_of_the_methods_it_calls(
    router: APIRouter, client: TestClient, recorder: Recorder
) -> None:
    assert _routes(router) == set(ROUTES) | set(TENANT_ROUTES)
    for (_, path), actions in TENANT_ROUTES.items():
        assert client.get(path).json() == [WORKSPACE]
        assert recorder.by(ALICE) == actions, path
    for (method, path), (last, actions) in ROUTES.items():
        url = path.replace("{workspace_id}", WORKSPACE)
        url = url[: url.rfind("{")] + last if last else url
        if method == "WEBSOCKET":
            with client.websocket_connect(url) as ws:
                ws.send_json({"type": "hello", "protocol": "artifactr.v1"})
                assert ws.receive_json()["type"] == "welcome"
                _wait_for(lambda: len(recorder.asked) == len(CONNECT))
        elif method == "POST":
            frame = {"type": "command", "command_id": "c1", "command": {"type": "create_thread"}}
            assert client.post(url, json=frame).status_code == 200
        else:
            assert client.get(url).status_code == 200, url
        assert recorder.by(ALICE) == ["artifactr:open", *actions], (method, path)


def test_every_route_answers_a_refusal_with_403(client: TestClient, recorder: Recorder) -> None:
    recorder.refused = ACTIONS - {"artifactr:open"}
    for (method, path), (last, _) in ROUTES.items():
        url = path.replace("{workspace_id}", WORKSPACE)
        url = url[: url.rfind("{")] + last if last else url
        if method == "POST":
            frame = {"type": "command", "command_id": "c1", "command": {"type": "create_thread"}}
            assert client.post(url, json=frame).status_code == 403, url
        elif method == "GET":
            assert client.get(url).status_code == 403, url


def test_every_websocket_command_asks_for_the_actions_of_the_methods_it_calls(
    client: TestClient, recorder: Recorder
) -> None:
    assert set(FRAMES) == _command_types() | {"stop_run", "watch_run"}
    with client.websocket_connect(f"/workspaces/{WORKSPACE}/stream") as ws:
        ws.send_json({"type": "hello", "protocol": "artifactr.v1"})
        _wait_for(lambda: len(recorder.asked) == len(CONNECT))
        recorder.asked.clear()
        for name, (fields, actions) in FRAMES.items():
            command = {"type": name, **fields}
            ws.send_json({"type": "command", "command_id": name, "command": command})
            while ws.receive_json().get("command_id") != name:
                pass
            assert recorder.by(ALICE) == actions, name


# ─── every MCP tool and resource ─────────────────────────────────────────────

TOOLS: dict[str, tuple[dict[str, Any], list[str]]] = {
    "list_artifacts": ({}, ["artifactr:read_artifacts"]),
    "read_artifact": ({"artifact_id": ARTIFACT}, ["artifactr:read_artifacts"]),
    "list_revisions": ({"artifact_id": ARTIFACT}, ["artifactr:read_artifacts"]),
    "create_artifact": ({"kind": "note", "data": {}}, ["artifactr:create_artifact"]),
    "edit_text": (
        {"artifact_id": ARTIFACT, "old": "Friday", "new": "Monday", "propose": True},
        ["artifactr:read_artifacts", "artifactr:propose_change"],
    ),
    "edit_artifact": (
        {"artifact_id": ARTIFACT, "base_version": 1, "ops": []},
        ["artifactr:edit_artifact"],
    ),
    "archive_artifact": (
        {"artifact_id": ARTIFACT},
        ["artifactr:read_artifacts", "artifactr:archive_artifact"],
    ),
    "list_proposals": ({}, ["artifactr:read_proposals"]),
    "respond_to_proposal": (
        {"proposal_id": PROPOSAL, "decision": "reject"},
        ["artifactr:respond_to_proposal"] * 2,  # of the workspace, then of the artifact
    ),
    "give_feedback": (
        {"feedback_type": "helpfulness", "target": {"kind": "thread", "thread_id": THREAD}},
        ["artifactr:give_feedback"],
    ),
    "list_threads": ({}, ["artifactr:read_threads"]),
    "get_thread": ({"thread_id": THREAD}, ["artifactr:read_threads"]),
    "post_message": (
        {"thread_id": THREAD, "content": "hi", "kind": "notice"},
        ["artifactr:post_message"],
    ),
    "get_run": ({"run_id": RUN}, ["artifactr:read_runs"]),
    "read_events": ({}, ["artifactr:read_events"]),
}
"""Each tool, arguments for it, and what its client is asked for after ``artifactr:open``."""

TENANT_TOOLS: dict[str, list[str]] = {"list_workspaces": [TENANT_WIDE, "artifactr:open"]}
"""Each tool that names no workspace, and what its client is asked for."""

OPEN_MCP = {
    "tools/list": "names no workspace: it lists what the server offers",
    "resources/templates/list": "names no workspace: it lists the artifact resource's template",
    "subscriptions/listen without an artifact": "names no workspace, so has nothing to refuse",
}
"""MCP requests that ask for nothing, and why."""


async def _resolve_client(ctx: object) -> tuple[TenantId, ExternalAgentActor]:
    return TENANT, CLIENT


@pytest.fixture
async def mcp(workspaces: Workspaces, runner: Runner[None]) -> AsyncIterator[ArtifactrMcp]:
    server = ArtifactrMcp(workspaces, runner, resolve=_resolve_client)
    yield server
    await server.aclose()


async def test_every_tool_and_resource_asks_for_the_actions_of_the_methods_it_calls(
    workspaces: Workspaces, recorder: Recorder, mcp: ArtifactrMcp
) -> None:
    await _seed(workspaces, recorder)
    async with Client(mcp.server) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == {
            *TOOLS,
            *TENANT_TOOLS,
        }
        assert len((await client.list_resource_templates()).resource_templates) == 1
        async with client.listen(tools_list_changed=True):
            pass
        assert recorder.asked == [], OPEN_MCP
        await client.call_tool("list_threads", {"workspace_id": WORKSPACE})
        # The server follows the workspace now, as itself: the log's head, then the log.
        notifier = SystemActor(name="mcp").participant
        for _ in range(200):
            if [p for p, _ in recorder.asked].count(notifier) == 2:
                break
            await asyncio.sleep(0.01)
        assert recorder.by(CLIENT) == ["artifactr:open", "artifactr:read_threads"]
        for tool, (args, actions) in TOOLS.items():
            result = await client.call_tool(tool, {"workspace_id": WORKSPACE, **args})
            content = result.content[0]
            assert isinstance(content, TextContent)
            assert recorder.by(CLIENT) == ["artifactr:open", *actions], (tool, content.text)
        for tool, actions in TENANT_TOOLS.items():
            await client.call_tool(tool, {})
            assert recorder.by(CLIENT) == actions, tool
        uri = artifact_uri(TENANT, WORKSPACE, ARTIFACT)
        await client.read_resource(uri)
        assert recorder.by(CLIENT) == ["artifactr:open", "artifactr:read_artifacts"]
        ws = await workspaces.open(TENANT, WORKSPACE, actor=ALICE)
        await ws.create(Note(), artifact_id="n2")
        recorder.by(ALICE)
        another = artifact_uri(TENANT, WORKSPACE, "n2")
        async with client.listen(resource_subscriptions=[uri, another]):
            pass
        read = "artifactr:read_artifacts"
        assert recorder.by(CLIENT) == ["artifactr:open", read, read], "each artifact is a read"


# ─── the catalog ─────────────────────────────────────────────────────────────


def test_the_catalog_is_every_action_asked_for_and_no_other() -> None:
    asked = {action for _, action in METHODS.values()}
    asked |= {action for _, actions in WORKSPACES_METHODS.values() for action in actions}
    asked |= {action for actions in TENANT_ROUTES.values() for action in actions}
    asked |= {action for actions in TENANT_TOOLS.values() for action in actions}
    asked |= {action for _, actions in FRAMES.values() for action in actions}
    asked |= {action for _, actions in ROUTES.values() for action in actions}
    asked |= {action for _, actions in TOOLS.values() for action in actions}
    asked.add(CREATE_NATIVE_FILE)  # native files' upload route asks it (tests/files/fastapi)
    asked.add(RUN_CODE)  # a connected app's toolset asks it beside the workspace (tests/connect)
    assert asked | {"artifactr:open"} == ACTIONS
