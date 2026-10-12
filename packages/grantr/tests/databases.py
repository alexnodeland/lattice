"""Empty databases for the SQL tests: a SQLite file, and PostgreSQL when it is configured.

The PostgreSQL tests run when ``GRANTR_TEST_POSTGRES_URL`` is set (``moon run grantr:pg-up``
starts a database, and ``moon run grantr:test-pg`` sets it); otherwise they are deselected.
Each test gets its own schema, dropped afterwards.
"""

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from grantr.sql import create_sqlite_engine, migrate

POSTGRES_URL = os.environ.get("GRANTR_TEST_POSTGRES_URL")

SQL_BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]

ROW_LEVEL_SECURITY = pytest.param("postgres-rls", marks=pytest.mark.postgres)
"""PostgreSQL as a role the row-level security policies hold, with the option on."""

APPLICATION_ROLE = "grantr_test_application"
"""The role the policies hold: it logs in, and owns nothing."""


@asynccontextmanager
async def empty_database(backend: str, directory: Path) -> AsyncIterator[AsyncEngine]:
    """Yield an engine on an empty database, and dispose of it (and the database) afterwards."""
    if backend == "sqlite":
        engine = create_sqlite_engine(f"sqlite+aiosqlite:///{directory / 'grantr.db'}")
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


def _engine(url: str | URL, schema: str) -> AsyncEngine:
    return create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})


@asynccontextmanager
async def row_level_security() -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """Yield the owner's engine on a migrated schema, and the engine of a role that isn't.

    The owner, which the migrations run as, bypasses the policies; the other role, which the
    migrations grant the tables, is held by them. Both are disposed of, and the schema dropped.
    """
    assert POSTGRES_URL, "PostgreSQL tests are deselected without a database"
    schema = f"test_{uuid.uuid4().hex}"
    admin = create_async_engine(POSTGRES_URL)
    async with admin.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        # Roles span the cluster, and tests may run side by side: create it once.
        await connection.exec_driver_sql(
            f"DO $$ BEGIN CREATE ROLE {APPLICATION_ROLE} LOGIN PASSWORD 'application';"
            " EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL; END $$"
        )
    owner = _engine(POSTGRES_URL, schema)
    await migrate(owner, application_role=APPLICATION_ROLE)
    url = make_url(POSTGRES_URL).set(username=APPLICATION_ROLE, password="application")
    application = _engine(url, schema)
    try:
        yield owner, application
    finally:
        await application.dispose()
        await owner.dispose()
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.dispose()
