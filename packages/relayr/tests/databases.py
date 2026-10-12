"""Empty databases for the SQL tests: a SQLite file, and PostgreSQL when it is configured.

The PostgreSQL tests run when ``RELAYR_TEST_POSTGRES_URL`` is set (``moon run relayr:pg-up``
starts a database, and ``moon run relayr:test-pg`` sets it); otherwise they are deselected.
Each test gets its own schema, dropped afterwards.
"""

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from relayr.sql import create_sqlite_engine

POSTGRES_URL = os.environ.get("RELAYR_TEST_POSTGRES_URL")

SQL_BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]


@asynccontextmanager
async def empty_database(backend: str, directory: Path) -> AsyncIterator[AsyncEngine]:
    """Yield an engine on an empty database, and dispose of it (and the database) afterwards."""
    if backend == "sqlite":
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{directory / 'relayr.db'}")
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    assert POSTGRES_URL, "PostgreSQL tests are deselected without a database"
    schema = f"test_{uuid.uuid4().hex}"
    admin = create_async_engine(POSTGRES_URL)
    async with admin.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_async_engine(
        POSTGRES_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.dispose()
