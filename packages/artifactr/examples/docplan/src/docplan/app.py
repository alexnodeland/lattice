"""The server: WebSocket and REST at /v1, MCP at /mcp.

Run it with ``docplan-serve`` (or ``uv run --package docplan docplan-serve``) and connect with
the ``docplan`` terminal client.

Workspaces are kept in memory, or in the database at ``DOCPLAN_DATABASE_URL`` (for example
``sqlite+aiosqlite:///docplan.db``), which is migrated to artifactr's schema at startup.

With ``OTEL_EXPORTER_OTLP_ENDPOINT`` set, docplan reports its traces, metrics and logs there;
with ``LANGFUSE_PUBLIC_KEY`` too, it files each turn in Langfuse and mirrors the ``main``
workspace's ratings to Langfuse scores. stackr's stack provides both.

Authentication here is a demo: the user is whatever the ``x-user`` header (or ``user`` query
parameter) says, and every user shares one tenant. Real applications resolve actors from their
own sessions or tokens.
"""

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator
from importlib.metadata import version
from typing import Any

import uvicorn
from fastapi import FastAPI
from pydantic_ai.models import Model
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.requests import HTTPConnection

from artifactr import InMemoryStorage, Runner, SystemActor, UserActor, Workspaces
from artifactr.core import Actor, ExternalAgentActor, TenantId
from artifactr.fastapi import artifactr_router
from artifactr.langfuse import LangfuseScoreConfigs, LangfuseScores, langfuse_turn
from artifactr.mcp import ArtifactrMcp
from artifactr.otel import TelemetryHandle, configure_telemetry
from artifactr.scores import FeedbackMirror, sync_score_configs
from artifactr.sql import SqlStorage, create_sqlite_engine, migrate
from artifactr.workspace import Storage
from docplan.agent import build_agent
from docplan.artifacts import Doc, Plan, Rating

TENANT: TenantId = "demo"
MIRRORED = "main"
"""The workspace whose ratings are mirrored to Langfuse: the terminal client's default."""


async def resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    """Demo authentication: trust the ``x-user`` header or ``user`` query parameter."""
    user = connection.headers.get("x-user") or connection.query_params.get("user") or "guest"
    return TENANT, UserActor(id=user, name=user)


async def resolve_client(_ctx: object) -> tuple[TenantId, ExternalAgentActor]:
    """Demo authentication for MCP clients: every client is one external agent."""
    return TENANT, ExternalAgentActor(client_id="mcp", name="MCP client")


def create_app(
    *,
    model: Model | str | None = None,
    storage: Storage | None = None,
    database_url: str | None = None,
    telemetry: TelemetryHandle | None = None,
) -> FastAPI:
    """Build the docplan application.

    Args:
        model: The agent's model; see :func:`docplan.agent.build_agent`.
        storage: Where workspaces live, if not in a database of docplan's own.
        database_url: A SQLAlchemy URL with an async driver, such as
            ``sqlite+aiosqlite:///docplan.db`` or ``postgresql+asyncpg://host/db``. Defaults to
            ``DOCPLAN_DATABASE_URL``. Without a storage or a URL, workspaces live in memory.
        telemetry: OpenTelemetry, set up by :func:`telemetry_from_environment`; also Langfuse
            when it has a client.
    """
    database_url = database_url or os.environ.get("DOCPLAN_DATABASE_URL")
    engine = open_database(database_url) if storage is None and database_url else None
    if engine is not None:
        storage = SqlStorage(engine)
    providers: dict[str, Any] = {}
    if telemetry is not None:
        providers = {
            "tracer_provider": telemetry.tracer_provider,
            "meter_provider": telemetry.meter_provider,
        }
    workspaces = Workspaces(storage or InMemoryStorage(), types=[Doc, Plan], **providers)
    langfuse = telemetry.langfuse if telemetry else None
    runner = Runner(
        build_agent(model, capabilities=[telemetry.capability()] if telemetry else []),
        app=None,
        agent_name="docplan",
        turn_context=langfuse_turn if langfuse else None,
        **providers,
    )
    mcp = ArtifactrMcp(workspaces, runner, resolve=resolve_client)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        async with contextlib.AsyncExitStack() as stack:
            if engine is not None:
                if telemetry is not None:
                    telemetry.instrument_engine(engine)
                await migrate(engine)
                stack.push_async_callback(engine.dispose)
            await stack.enter_async_context(mcp.lifespan())
            if langfuse is not None:
                await sync_score_configs(LangfuseScoreConfigs(langfuse), [Rating])
                workspace = await workspaces.open(TENANT, MIRRORED, actor=SystemActor())
                mirror = FeedbackMirror(workspace, LangfuseScores(langfuse))
                stack.push_async_callback(_cancel, asyncio.create_task(mirror.follow()))
            yield

    app = FastAPI(title="docplan", lifespan=lifespan)
    app.include_router(
        artifactr_router(workspaces, runner, resolve_actor=resolve_actor, **providers),
        prefix="/v1",
    )
    app.mount("/mcp", mcp.http_app(streamable_http_path="/"))
    if telemetry is not None:
        telemetry.instrument_app(app)

    @app.get("/")
    async def about() -> dict[str, str]:
        return {
            "name": "docplan",
            "stream": "/v1/workspaces/{workspace_id}/stream",
            "commands": "/v1/workspaces/{workspace_id}/commands",
            "mcp": "/mcp",
        }

    return app


def open_database(url: str) -> AsyncEngine:
    """Create an engine for ``url``; SQLite needs artifactr's own engine settings."""
    if make_url(url).get_backend_name() == "sqlite":
        return create_sqlite_engine(url)
    return create_async_engine(url)


def telemetry_from_environment() -> TelemetryHandle | None:
    """Set up OpenTelemetry, and Langfuse, as the environment asks.

    OpenTelemetry when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, and Langfuse with it when
    ``LANGFUSE_PUBLIC_KEY`` is set; otherwise, nothing.
    """
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    return configure_telemetry(
        service_name="docplan",
        service_version=version("docplan"),
        environment=os.environ.get("DOCPLAN_ENVIRONMENT", "development"),
        langfuse=bool(os.environ.get("LANGFUSE_PUBLIC_KEY")),
    )


async def _cancel(task: "asyncio.Task[None]") -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def main() -> None:
    """Serve docplan on ``DOCPLAN_HOST``:``DOCPLAN_PORT`` (default 127.0.0.1:8000)."""
    host = os.environ.get("DOCPLAN_HOST", "127.0.0.1")
    port = int(os.environ.get("DOCPLAN_PORT", "8000"))
    telemetry = telemetry_from_environment()
    try:
        uvicorn.run(create_app(telemetry=telemetry), host=host, port=port)
    finally:
        if telemetry is not None:
            telemetry.shutdown()
