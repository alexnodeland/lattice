"""The permission matrix (lattice RFC-0001, ADR-0056): every way in asks ``authorize``.

Every public ``Workspace`` method, and each ``Workspaces`` method that reads across a tenant, is
listed with the action it asks for, and every REST route, WebSocket command, and MCP tool and
resource with the actions its caller is asked for, which are those of the methods it calls.
Each is called with a hook that records what it is asked. A method or surface missing from the
tables fails, as does one that asks for an action outside :data:`~reflexr.workspace.ACTIONS`, or
one that asks for nothing. What is open on purpose is listed with its reason, and asks nothing.
"""

import asyncio
import contextlib
import inspect
import time
import typing
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient
from mcp import Client
from starlette.requests import HTTPConnection

from reflexr import Actor, Feedback, Rule, SystemActor, UserActor, on, run
from reflexr.core import (
    Command,
    ExternalAgentActor,
    Rejection,
    RunTarget,
    StoredRules,
    TenantId,
    WorkspaceId,
)
from reflexr.fastapi import reflexr_router
from reflexr.mcp import ReflexrMcp, run_uri
from reflexr.workspace import ACTIONS, Access, InMemoryStorage, Schedule, Workspace, Workspaces
from tests.event_types import Deploy

TENANT, WORKSPACE = "acme", "prod"
ADA = UserActor(id="ada")
CLIENT = ExternalAgentActor(client_id="claude")
RUN = "run_1"
STORED = Rule(
    name="chat:deploys",
    when=on(Deploy).at_most(10, per=timedelta(hours=1)),
    then=run("note"),
    ordering="none",
    timeout=timedelta(minutes=1),
)


class MatrixUseful(Feedback, name="matrix_useful", targets={"run"}):
    useful: bool


class Recorder:
    """An ``authorize`` hook that allows everything and records what it is asked, by whom."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, WorkspaceId | None, Access]] = []

    async def __call__(
        self, tenant_id: TenantId, workspace_id: WorkspaceId | None, actor: Actor, access: Access
    ) -> bool:
        assert tenant_id == TENANT
        self.asked.append((actor.participant, workspace_id, access))
        return True

    def actions(self) -> list[str]:
        return [access.action for _, _, access in self.asked]

    def by(self, actor: Actor, workspace_id: WorkspaceId | None = WORKSPACE) -> list[str]:
        """What ``actor`` was asked for, in order, all in one workspace; and forget it all."""
        asked = [(w, access) for p, w, access in self.asked if p == actor.participant]
        self.asked.clear()
        assert {w for w, _ in asked} <= {workspace_id}, asked
        return [access.action for _, access in asked]


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def workspaces(recorder: Recorder) -> Workspaces:
    return Workspaces(
        InMemoryStorage(),
        events=[Deploy],
        rules=[Rule(name="app:deploys", when=on(Deploy), then=run("note"))],
        stored_rules=StoredRules(actions={"note": None}, namespaces={"chat"}),
        schedules=[Schedule(name="heartbeat", every=timedelta(minutes=1))],
        authorize=recorder,
    )


# ─── every public Workspace method, and the reads across a tenant ────────────

type Call = Callable[[Workspace], Awaitable[object]]


async def _subscribe(ws: Workspace) -> None:
    stream = ws.subscribe()
    await asyncio.wait_for(anext(stream), timeout=0.01)


METHODS: dict[str, tuple[Call, Access]] = {
    "publish": (lambda ws: ws.publish(Deploy(service="auth")), Access(action="reflexr:publish")),
    "publish_many": (
        lambda ws: ws.publish_many([Deploy(service="auth")]),
        Access(action="reflexr:publish"),
    ),
    "give_feedback": (
        lambda ws: ws.give_feedback(MatrixUseful(useful=True), on=RunTarget(run_id=RUN)),
        Access(action="reflexr:give_feedback"),
    ),
    "retry_run": (lambda ws: ws.retry_run(RUN), Access(action="reflexr:retry_run")),
    "skip_run": (lambda ws: ws.skip_run(RUN), Access(action="reflexr:skip_run")),
    "cancel_run": (lambda ws: ws.cancel_run(RUN), Access(action="reflexr:cancel_run")),
    "checkpoint_run": (
        lambda ws: ws.checkpoint_run(RUN, attempt=1, step="s", state=None),
        Access(action="reflexr:checkpoint_run"),
    ),
    "replay_rule": (
        lambda ws: ws.replay_rule("app:deploys"),
        Access(action="reflexr:replay_rule", rule="app:deploys"),
    ),
    "install_rule": (
        lambda ws: ws.install_rule(STORED),
        Access(action="reflexr:install_rule", rule=STORED.name),
    ),
    "update_rule": (
        lambda ws: ws.update_rule(STORED),
        Access(action="reflexr:update_rule", rule=STORED.name),
    ),
    "archive_rule": (
        lambda ws: ws.archive_rule(STORED.name),
        Access(action="reflexr:archive_rule", rule=STORED.name),
    ),
    "head_seq": (lambda ws: ws.head_seq(), Access(action="reflexr:read_events")),
    "read": (lambda ws: ws.read(), Access(action="reflexr:read_events")),
    "subscribe": (_subscribe, Access(action="reflexr:read_events")),
    "cursor": (lambda ws: ws.cursor("c"), Access(action="reflexr:read_cursors")),
    "save_cursor": (lambda ws: ws.save_cursor("c", 1), Access(action="reflexr:save_cursor")),
    "run": (lambda ws: ws.run(RUN), Access(action="reflexr:read_runs")),
    "runs": (
        lambda ws: ws.runs(rule="app:deploys"),
        Access(action="reflexr:read_runs", rule="app:deploys"),
    ),
    "dead_letters": (
        lambda ws: ws.dead_letters(rule="app:deploys"),
        Access(action="reflexr:read_dead_letters", rule="app:deploys"),
    ),
    "schedule_ticks": (lambda ws: ws.schedule_ticks(), Access(action="reflexr:read_schedules")),
    "schedule_statuses": (
        lambda ws: ws.schedule_statuses(),
        Access(action="reflexr:read_schedules"),
    ),
    "rule_progress": (lambda ws: ws.rule_progress(), Access(action="reflexr:read_rules")),
    "rule_statuses": (lambda ws: ws.rule_statuses(), Access(action="reflexr:read_rules")),
    "get_rule": (
        lambda ws: ws.get_rule("app:deploys"),
        Access(action="reflexr:read_rules", rule="app:deploys"),
    ),
}
"""Each public ``Workspace`` method, a call of it, and the one ``Access`` it asks for."""

OPEN_METHODS = {
    "tenant_id": "a property: the handle's own tenant",
    "workspace_id": "a property: the handle's own workspace",
    "actor": "a property: whom the handle acts as",
    "telemetry": "a property: the tracer and instruments, for actions' own spans",
    "causation": "a property: what caused the handle's events, if a run did",
    "as_actor": "derives a handle for another actor, whose methods ask as that actor",
    "caused_by": "derives a handle for a run's events, whose methods ask as its actor",
    "check": "is the asking itself: what every other method calls",
}
"""Public ``Workspace`` methods that ask for no action of their own, and why."""

TENANT_WIDE: dict[str, tuple[Callable[[Workspaces], Awaitable[object]], str]] = {
    "rules_for": (lambda w: w.rules_for(TENANT, actor=ADA), "reflexr:read_rules"),
    "schedules_for": (lambda w: w.schedules_for(TENANT, actor=ADA), "reflexr:read_schedules"),
}
"""The ``Workspaces`` methods that read across a tenant, which ask with no workspace."""

OPEN_WORKSPACES = {
    "storage": "the reactor's: where workspaces are kept, for its own work beneath the hook",
    "rules": "configuration: the code rules, which the reactor evaluates; clients read rules_for",
    "schedules": "configuration: the schedules the reactor ticks; clients read schedules_for",
    "stored_rules": "configuration: what stored rules may do",
    "predicates": "configuration: the predicates rules refer to",
    "clock": "configuration: the time for run transitions",
    "max_depth": "configuration: the deepest causal chain",
    "telemetry": "configuration: the tracer and instruments",
    "open": "asks reflexr:open, as every surface's request shows below",
    "execute": "carries a command out through the handle's methods, which ask",
    "rules_in": "the reactor's: it reads a workspace's rules for its own work, beneath the hook",
}
"""The other public ``Workspaces`` methods, and why each asks nothing of its own."""


def _public(cls: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_") and (inspect.isfunction(member) or isinstance(member, property))
    }


def test_every_public_method_is_listed() -> None:
    assert _public(Workspace) == set(METHODS) | set(OPEN_METHODS)
    assert _public(Workspaces) == set(TENANT_WIDE) | set(OPEN_WORKSPACES)


@pytest.mark.parametrize("method", sorted(METHODS))
async def test_each_method_asks_for_its_action_once(
    workspaces: Workspaces, recorder: Recorder, method: str
) -> None:
    ws = await workspaces.open(TENANT, WORKSPACE, actor=ADA)
    recorder.asked.clear()
    call, access = METHODS[method]
    with contextlib.suppress(Rejection, TimeoutError):  # asked, then refused, or waiting
        await call(ws)
    assert [asked for _, _, asked in recorder.asked] == [access]
    assert access.action in ACTIONS


@pytest.mark.parametrize("method", sorted(TENANT_WIDE))
async def test_a_read_across_the_tenant_asks_with_no_workspace(
    workspaces: Workspaces, recorder: Recorder, method: str
) -> None:
    call, action = TENANT_WIDE[method]
    await call(workspaces)
    assert recorder.by(ADA, None) == [action]


def _command_types() -> set[str]:
    [union, _] = typing.get_args(Command.__value__)
    return {model.model_fields["type"].default for model in typing.get_args(union)}


# ─── every WebSocket command, and every REST route ───────────────────────────

DEPLOY = {"type": "app:deploy.finished", "service": "auth"}

FRAMES: dict[str, dict[str, Any]] = {
    "publish": {"event": DEPLOY},
    "give_feedback": {
        "feedback_type": "matrix_useful",
        "target": {"kind": "run", "run_id": RUN},
        "value": {"useful": True},
    },
    "retry_run": {"run_id": RUN},
    "skip_run": {"run_id": RUN},
    "cancel_run": {"run_id": RUN},
    "replay_rule": {"rule": "app:deploys"},
    "install_rule": {"rule": STORED.model_dump(mode="json")},
    "update_rule": {"rule": STORED.model_dump(mode="json")},
    "archive_rule": {"rule": STORED.name},
}
"""Fields for each command a client may send; each asks for the action named by its type."""

CONNECT = ["reflexr:open", "reflexr:read_events", "reflexr:read_events"]
"""What a WebSocket connection is asked for as it opens: its workspace, the log's head
(welcome), then the log it follows."""

ROUTES: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("POST", "/workspaces/{workspace_id}/commands"): ("", ["reflexr:publish"]),
    ("POST", "/workspaces/{workspace_id}/events"): ("", ["reflexr:publish"]),
    ("GET", "/workspaces/{workspace_id}/events"): ("", ["reflexr:read_events"]),
    ("GET", "/rules"): ("", ["reflexr:read_rules"]),
    ("GET", "/workspaces/{workspace_id}/rules"): ("", ["reflexr:read_rules"]),
    ("GET", "/workspaces/{workspace_id}/rules/{rule}"): ("app:deploys", ["reflexr:read_rules"]),
    ("GET", "/workspaces/{workspace_id}/runs"): ("", ["reflexr:read_runs"]),
    ("GET", "/workspaces/{workspace_id}/runs/{run_id}"): (RUN, ["reflexr:read_runs"]),
    ("GET", "/workspaces/{workspace_id}/dead-letters"): ("", ["reflexr:read_dead_letters"]),
    ("GET", "/schedules"): ("", ["reflexr:read_schedules"]),
    ("GET", "/workspaces/{workspace_id}/schedules"): ("", ["reflexr:read_schedules"]),
    ("WEBSOCKET", "/workspaces/{workspace_id}/stream"): ("", CONNECT[1:]),
}
"""Each route, the id its path names last, if any, and what its caller is asked for after
``reflexr:open``: no open for ``/rules`` and ``/schedules``, which read across the tenant."""


async def _resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    return TENANT, ADA


@pytest.fixture
def router(workspaces: Workspaces) -> APIRouter:
    return reflexr_router(workspaces, resolve_actor=_resolve_actor)


@pytest.fixture
def client(router: APIRouter) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
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
    assert _routes(router) == set(ROUTES)
    for (method, path), (last, actions) in ROUTES.items():
        url = path.replace("{workspace_id}", WORKSPACE)
        url = url[: url.rfind("{")] + last if last else url
        if method == "WEBSOCKET":
            with client.websocket_connect(url) as ws:
                ws.send_json({"type": "hello", "protocol": "reflexr.v1"})
                assert ws.receive_json()["type"] == "welcome"
                _wait_for(lambda: len(recorder.asked) == len(CONNECT))
        elif method == "POST":
            body = {"event": DEPLOY}
            if path.endswith("commands"):
                body = {"type": "command", "command_id": "c1", "command": {"type": "publish"}}
                body["command"] |= {"event": DEPLOY}
            client.post(url, json=body)
        else:
            client.get(url)
        workspace = None if "{workspace_id}" not in path else WORKSPACE
        opened = [] if workspace is None else ["reflexr:open"]
        assert recorder.by(ADA, workspace) == [*opened, *actions], (method, path)


def test_every_websocket_command_asks_for_the_action_its_type_names(
    client: TestClient, recorder: Recorder
) -> None:
    assert set(FRAMES) == _command_types()
    with client.websocket_connect(f"/workspaces/{WORKSPACE}/stream") as ws:
        ws.send_json({"type": "hello", "protocol": "reflexr.v1"})
        _wait_for(lambda: len(recorder.asked) == len(CONNECT))
        recorder.asked.clear()
        for name, fields in FRAMES.items():
            command = {"type": name, **fields}
            ws.send_json({"type": "command", "command_id": name, "command": command})
            while ws.receive_json().get("command_id") != name:
                pass
            assert recorder.by(ADA) == [f"reflexr:{name}"], name


# ─── every MCP tool and resource ─────────────────────────────────────────────

TOOLS: dict[str, tuple[dict[str, Any], list[str]]] = {
    "publish_event": ({"event": DEPLOY}, ["reflexr:publish"]),
    "read_events": ({}, ["reflexr:read_events"]),
    "rule_status": ({}, ["reflexr:read_rules"]),
    "get_rule": ({"rule": "app:deploys"}, ["reflexr:read_rules"]),
    "schedule_status": ({}, ["reflexr:read_schedules"]),
    "replay_rule": ({"rule": "app:deploys"}, ["reflexr:replay_rule"]),
    "install_rule": ({"rule": STORED.model_dump(mode="json")}, ["reflexr:install_rule"]),
    "update_rule": ({"rule": STORED.model_dump(mode="json")}, ["reflexr:update_rule"]),
    "archive_rule": ({"rule": STORED.name}, ["reflexr:archive_rule"]),
    "list_runs": ({}, ["reflexr:read_runs"]),
    "get_run": ({"run_id": RUN}, ["reflexr:read_runs"]),
    "retry_run": ({"run_id": RUN}, ["reflexr:retry_run"]),
    "skip_run": ({"run_id": RUN}, ["reflexr:skip_run"]),
    "cancel_run": ({"run_id": RUN}, ["reflexr:cancel_run"]),
    "list_dead_letters": ({}, ["reflexr:read_dead_letters"]),
    "give_feedback": (
        {
            "feedback_type": "matrix_useful",
            "target": {"kind": "run", "run_id": RUN},
            "value": {"useful": True},
        },
        ["reflexr:give_feedback"],
    ),
}
"""Each tool that names a workspace, arguments for it, and what its client is asked for after
``reflexr:open``. ``list_rules`` reads across the tenant, and asks ``reflexr:read_rules`` alone."""

OPEN_MCP = {
    "tools/list": "names no workspace: it lists what the server offers",
    "resources/templates/list": "names no workspace: it lists the run resource's template",
    "subscriptions/listen without a run": "names no workspace, so has nothing to refuse",
}
"""MCP requests that ask for nothing, and why."""


async def _resolve_client(ctx: object) -> tuple[TenantId, ExternalAgentActor]:
    return TENANT, CLIENT


@pytest.fixture
async def mcp(workspaces: Workspaces) -> AsyncIterator[ReflexrMcp]:
    server = ReflexrMcp(workspaces, resolve=_resolve_client)
    yield server
    await server.aclose()


async def test_every_tool_and_resource_asks_for_the_actions_of_the_methods_it_calls(
    recorder: Recorder, mcp: ReflexrMcp
) -> None:
    async with Client(mcp.server) as client:
        served = {tool.name for tool in (await client.list_tools()).tools}
        assert served == {*TOOLS, "list_rules"}
        assert len((await client.list_resource_templates()).resource_templates) == 1
        async with client.listen(tools_list_changed=True):
            pass
        assert recorder.asked == [], OPEN_MCP
        await client.call_tool("list_rules", {})
        assert recorder.by(CLIENT, None) == ["reflexr:read_rules"]
        await client.call_tool("read_events", {"workspace_id": WORKSPACE})
        # The server follows the workspace now, as itself: the log's head, then the log.
        notifier = SystemActor(name="mcp").participant
        for _ in range(200):
            if [p for p, _, _ in recorder.asked].count(notifier) == 2:
                break
            await asyncio.sleep(0.01)
        assert recorder.by(CLIENT) == ["reflexr:open", "reflexr:read_events"]
        for tool, (args, actions) in TOOLS.items():
            await client.call_tool(tool, {"workspace_id": WORKSPACE, **args})
            assert recorder.by(CLIENT) == ["reflexr:open", *actions], tool
        uri = run_uri(TENANT, WORKSPACE, RUN)
        with pytest.raises(Exception, match="run run_1 does not exist"):
            await client.read_resource(uri)
        assert recorder.by(CLIENT) == ["reflexr:open", "reflexr:read_runs"]
        another = run_uri(TENANT, WORKSPACE, "run_2")
        async with client.listen(resource_subscriptions=[uri, another]):
            pass
        read = "reflexr:read_runs"
        assert recorder.by(CLIENT) == ["reflexr:open", read, read], "each run is a read"


# ─── the catalog ─────────────────────────────────────────────────────────────


def test_the_catalog_is_every_action_asked_for_and_no_other() -> None:
    asked = {access.action for _, access in METHODS.values()}
    asked |= {action for _, action in TENANT_WIDE.values()}
    asked |= {f"reflexr:{name}" for name in FRAMES}
    asked |= {action for _, actions in ROUTES.values() for action in actions}
    asked |= {action for _, actions in TOOLS.values() for action in actions}
    assert asked | {"reflexr:open"} == ACTIONS
