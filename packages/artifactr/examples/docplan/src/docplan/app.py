"""The server: WebSocket and REST at /v1, MCP at /mcp.

Run it with ``docplan-serve`` (or ``uv run --package docplan docplan-serve``) and connect with
the ``docplan`` terminal client.

Authentication here is a demo: the user is whatever the ``x-user`` header (or ``user`` query
parameter) says, and every user shares one tenant. Real applications resolve actors from their
own sessions or tokens.
"""

import contextlib
import os
from collections.abc import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from pydantic_ai.models import Model
from starlette.requests import HTTPConnection

from artifactr import InMemoryStorage, Runner, UserActor, Workspaces
from artifactr.core import Actor, ExternalAgentActor, TenantId
from artifactr.fastapi import artifactr_router
from artifactr.mcp import ArtifactrMcp
from artifactr.workspace import Storage
from docplan.agent import build_agent
from docplan.artifacts import Doc, Plan

TENANT: TenantId = "demo"


async def resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    """Demo authentication: trust the ``x-user`` header or ``user`` query parameter."""
    user = connection.headers.get("x-user") or connection.query_params.get("user") or "guest"
    return TENANT, UserActor(id=user, name=user)


async def resolve_client(_ctx: object) -> tuple[TenantId, ExternalAgentActor]:
    """Demo authentication for MCP clients: every client is one external agent."""
    return TENANT, ExternalAgentActor(client_id="mcp", name="MCP client")


def create_app(*, model: Model | str | None = None, storage: Storage | None = None) -> FastAPI:
    """Build the docplan application.

    Args:
        model: The agent's model; see :func:`docplan.agent.build_agent`.
        storage: Where workspaces live. Defaults to in-memory storage.
    """
    workspaces = Workspaces(storage or InMemoryStorage(), types=[Doc, Plan])
    runner = Runner(build_agent(model), app=None, agent_name="docplan")
    mcp = ArtifactrMcp(workspaces, runner, resolve=resolve_client)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        async with mcp.lifespan():
            yield

    app = FastAPI(title="docplan", lifespan=lifespan)
    app.include_router(
        artifactr_router(workspaces, runner, resolve_actor=resolve_actor), prefix="/v1"
    )
    app.mount("/mcp", mcp.http_app(streamable_http_path="/"))

    @app.get("/")
    async def about() -> dict[str, str]:
        return {
            "name": "docplan",
            "stream": "/v1/workspaces/{workspace_id}/stream",
            "commands": "/v1/workspaces/{workspace_id}/commands",
            "mcp": "/mcp",
        }

    return app


def main() -> None:
    """Serve docplan on ``DOCPLAN_HOST``:``DOCPLAN_PORT`` (default 127.0.0.1:8000)."""
    host = os.environ.get("DOCPLAN_HOST", "127.0.0.1")
    port = int(os.environ.get("DOCPLAN_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)
