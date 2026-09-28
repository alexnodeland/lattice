"""An application built from the router, with a scripted agent and header-based auth."""

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent, FunctionToolset, RunContext
from starlette.requests import HTTPConnection

import tests.artifact_types  # noqa: F401  (registers the test artifact types)
from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import Actor, TenantId, UserActor, WorkspaceId
from artifactr.fastapi import Unauthorized, artifactr_router
from artifactr.workspace import InMemoryStorage, Workspaces
from tests.agent.conftest import Script
from tests.artifact_types import Checklist, Note


class Latch:
    """Holds a tool call open across threads until the test releases it."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()

    async def wait(self) -> None:
        self.entered.set()
        await asyncio.to_thread(self.released.wait, 5)


def latch_tools() -> FunctionToolset[Session[Latch]]:
    tools = FunctionToolset[Session[Latch]]()

    @tools.tool
    async def hold(ctx: RunContext[Session[Latch]]) -> str:
        """Wait for the test."""
        await ctx.deps.app.wait()
        return "released"

    return tools


async def resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    if connection.headers.get("x-token") == "bad":
        raise Unauthorized("bad token")
    return connection.headers.get("x-tenant", "tenant"), UserActor(
        id=connection.headers.get("x-user", "alice")
    )


async def authorize(tenant_id: TenantId, workspace_id: WorkspaceId, actor: Actor) -> bool:
    return workspace_id != "secret"


def build(
    script: Script, *, latch: Latch | None = None, **options: Any
) -> tuple[FastAPI, Runner[Latch]]:
    agent: Agent[Session[Latch], Any] = Agent(
        script.model,
        deps_type=Session[Latch],
        toolsets=[latch_tools()],
        capabilities=[ArtifactWorkspace(types=[Note, Checklist])],
    )
    runner = Runner(agent, app=latch or Latch())
    workspaces = Workspaces(InMemoryStorage(), types=[Note, Checklist])
    app = FastAPI()
    router = artifactr_router(
        workspaces, runner, resolve_actor=resolve_actor, authorize=authorize, **options
    )
    app.include_router(router, prefix="/v1")
    return app, runner


@pytest.fixture
def client() -> Iterator[TestClient]:
    app, _ = build(Script())
    with TestClient(app) as client:
        yield client


def command(command_id: str, **command: Any) -> dict[str, Any]:
    return {"type": "command", "command_id": command_id, "command": command}


def hello(**options: Any) -> dict[str, Any]:
    return {"type": "hello", "protocol": "artifactr.v1", **options}


def wait_for(check: Callable[[], bool], timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "timed out waiting"
        time.sleep(0.01)
