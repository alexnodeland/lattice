"""Module to handle all security operations."""

import logging
from collections.abc import Generator

from sqlmodel import Session, create_engine
from uvicorn.logging import ColourizedFormatter

from artifactr.config import get_settings
from artifactr.db import DatabaseManager

settings = get_settings()

# Create a global engine instance to be used across the application
engine = None
try:
    if settings.db_url:
        engine = create_engine(
            str(settings.db_url),
            echo=True,
            # For SQLite, allow using connections across threads
            connect_args={"check_same_thread": False}
            if str(settings.db_url).startswith("sqlite")
            else {},
        )
    else:
        # Use SQLite in-memory database as fallback
        logger = logging.getLogger(__name__)
        logger.warning(
            "No db_url provided, using SQLite in-memory database as fallback"
        )
        engine = create_engine(
            "sqlite:///:memory:",
            echo=True,
            # Important: Allow using SQLite connections across threads
            connect_args={"check_same_thread": False},
        )
except Exception as e:
    if settings.mode == "prod":
        raise e

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(
    ColourizedFormatter(
        "{levelprefix:<8} {filename} : {lineno} : {name} : {message}",
        style="{",
        use_colors=True,
    )
)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def get_session():
    """Get a new database session for FastAPI endpoints."""
    with Session(engine) as session:
        yield session


def get_db() -> Generator[DatabaseManager, None, None]:
    """Get a new database manager instance for FastAPI endpoints."""
    with Session(engine) as session:
        yield DatabaseManager(session)


def get_db_direct():
    """Get a new database session for MCP tools."""
    if engine is None:
        logger.error("Database engine is not initialized")
        raise ValueError("Database engine is not initialized")
    return DatabaseManager(Session(engine))


def get_db_session():
    """Create a new database session for MCP tools."""
    if engine is None:
        logger.error("Database engine is not initialized")
        raise ValueError("Database engine is not initialized")
    return Session(engine)


def get_logger():
    """Get the exchange logger."""
    return logger
