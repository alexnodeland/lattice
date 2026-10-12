"""Empty databases for the SQL tests: a SQLite file, and PostgreSQL when it is configured.

The PostgreSQL tests run when ``REFLEXR_TEST_POSTGRES_URL`` is set (``make pg-up`` starts a
database, and ``make test-pg`` sets it); otherwise they are deselected. Each test gets its own
schema, dropped afterwards.
"""

import os
import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from reflexr.sql import create_sqlite_engine, migrate

POSTGRES_URL = os.environ.get("REFLEXR_TEST_POSTGRES_URL")

SQL_BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]

ROW_LEVEL_SECURITY = pytest.param("postgres-rls", marks=pytest.mark.postgres)
"""PostgreSQL as a role the row-level security policies hold, with the option on."""

APPLICATION_ROLE = "reflexr_test_application"
"""The role the policies hold: it logs in, and owns nothing."""


@dataclass
class Database:
    """An empty database, and the engines a test opens on it."""

    connect: Callable[[timedelta | None], AsyncEngine]
    engines: list[AsyncEngine] = field(default_factory=list[AsyncEngine])

    def engine(self, *, lock_timeout: timedelta | None = None) -> AsyncEngine:
        """Open another engine on the database, as another process would.

        With a ``lock_timeout``, a statement that waits longer than that for another
        transaction's lock fails, rather than waiting as long as the database lets it.
        """
        engine = self.connect(lock_timeout)
        self.engines.append(engine)
        return engine

    async def dispose(self) -> None:
        for engine in self.engines:
            await engine.dispose()


@asynccontextmanager
async def empty_database(backend: str, directory: Path) -> AsyncGenerator[Database]:
    """Yield an empty database, and dispose of its engines (and it) afterwards."""
    if backend == "sqlite":
        url = f"sqlite+aiosqlite:///{directory / 'reflexr.db'}"

        def connect_sqlite(lock_timeout: timedelta | None) -> AsyncEngine:
            waits = {} if lock_timeout is None else {"timeout": lock_timeout.total_seconds()}
            return create_sqlite_engine(url, connect_args=waits)

        database = Database(connect_sqlite)
        try:
            yield database
        finally:
            await database.dispose()
        return
    assert POSTGRES_URL, "PostgreSQL tests are deselected without a database"
    url = POSTGRES_URL
    schema = f"test_{uuid.uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

    def connect_postgres(lock_timeout: timedelta | None) -> AsyncEngine:
        settings = {"search_path": schema}
        if lock_timeout is not None:
            settings["lock_timeout"] = f"{lock_timeout.total_seconds() * 1000:.0f}"
        return create_async_engine(url, connect_args={"server_settings": settings})

    database = Database(connect_postgres)
    try:
        yield database
    finally:
        await database.dispose()
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.dispose()


def _engine(url: str | URL, schema: str) -> AsyncEngine:
    return create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})


@asynccontextmanager
async def row_level_security() -> AsyncGenerator[tuple[AsyncEngine, AsyncEngine]]:
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
