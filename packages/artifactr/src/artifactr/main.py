"""Main module for the backend."""

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from sqlmodel import SQLModel

from artifactr.config import get_settings
from artifactr.dependencies import engine, get_logger
from artifactr.routers import agent, idea, root, thread, types, user, ws
from artifactr.services.agent import build_idea_agent

settings = get_settings()
logger = get_logger()

# Initialize the MCP server
mcp_server_idea = FastMCP(
    name="IdeaManager",
    port=settings.mcp_idea_port,
    host=settings.mcp_idea_host,
)


def run_mcp_server_idea_thread():
    """Run the MCP server in a separate thread."""
    logger.info(
        f"Starting MCP server on {settings.mcp_idea_host}:{settings.mcp_idea_port}..."
    )
    try:
        # The run method is blocking, so we run it in a thread
        mcp_server_idea.run(transport="sse")
    except Exception as e:
        logger.error(f"MCP Server error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Define the lifespan handlers for the application."""
    logger.info("Connecting to engine...")

    # Create the database tables first
    if engine is not None:
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables created successfully")

    # Start the MCP server
    logger.info(f"Starting MCP server on port {settings.mcp_idea_port}...")
    thread = threading.Thread(target=run_mcp_server_idea_thread, daemon=True)
    thread.start()

    # Give the MCP server a moment to start up
    time.sleep(2)

    # Initialize MCP-based agents
    app.state.idea_agent = build_idea_agent(
        settings.mcp_idea_host, settings.mcp_idea_port
    )

    # Initialize MCP server context
    app.state.mcp_idea_cm = app.state.idea_agent.run_mcp_servers()

    try:
        # Enter the context manager
        await app.state.mcp_idea_cm.__aenter__()
        logger.info("MCP server context initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MCP server context: {e}")

    yield

    # Clean up MCP context if it exists
    if hasattr(app.state, "mcp_idea_cm"):
        try:
            await app.state.mcp_idea_cm.__aexit__(None, None, None)
            logger.info("MCP server context closed")
        except Exception as e:
            logger.error(f"Error closing MCP server context: {e}")

    # Create the database and tables
    if settings.mode == "development" and engine is not None:
        SQLModel.metadata.drop_all(engine)

    # After shutdown
    logger.info("Shutting down engine...")


app = FastAPI(
    title=settings.title,
    description=settings.description,
    contact={"email": settings.support_email},
    version=str(settings.version),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:8080",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(root.router, tags=["root"])
app.include_router(user.router, prefix="/users", tags=["users"])
app.include_router(idea.router, prefix="/idea", tags=["idea"])
app.include_router(thread.router, prefix="/threads", tags=["threads"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])
app.include_router(types.router, prefix="/types", tags=["types"])
app.include_router(ws.router, tags=["websocket"])
