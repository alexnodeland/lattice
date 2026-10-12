"""The packaged migrations build exactly the schema the models describe."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from relayr.sql import create_schema, migrate
from relayr.sql.schema import _alembic_config
from relayr.sql.tables import VERSION_TABLE, metadata
from tests.databases import empty_database


def _differences(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(connection, opts={"version_table": VERSION_TABLE})
    return compare_metadata(context, metadata)


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


async def test_migrations_build_the_models_schema(engine: AsyncEngine) -> None:
    await migrate(engine)
    async with engine.connect() as connection:
        assert await connection.run_sync(_differences) == []
        assert await connection.run_sync(_tables) == {*metadata.tables, VERSION_TABLE}


async def test_migrating_an_up_to_date_database_changes_nothing(engine: AsyncEngine) -> None:
    await migrate(engine)
    await migrate(engine)
    async with engine.connect() as connection:
        assert await connection.run_sync(_differences) == []


async def test_migrations_downgrade_to_an_empty_database(engine: AsyncEngine) -> None:
    await migrate(engine)
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "base"))
        assert await connection.run_sync(_tables) == {VERSION_TABLE}


async def test_create_schema_builds_the_same_schema(engine: AsyncEngine) -> None:
    await create_schema(engine)
    async with engine.connect() as connection:
        assert await connection.run_sync(_tables) == set(metadata.tables)
        assert await connection.run_sync(_differences) == []


ROW_SECURITY = text(
    "SELECT relrowsecurity FROM pg_class"
    " WHERE relnamespace = current_schema()::regnamespace AND relkind = 'r'"
)
POLICIES = text(
    "SELECT policyname, cmd, qual, with_check FROM pg_policies"
    " WHERE schemaname = current_schema() ORDER BY policyname"
)


@pytest.fixture
async def postgres(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    async with empty_database("postgres", tmp_path) as engine:
        yield engine


async def _row_security(engine: AsyncEngine) -> list[bool]:
    async with engine.connect() as connection:
        return list(await connection.scalars(ROW_SECURITY))


async def _policies(engine: AsyncEngine) -> list[tuple[Any, ...]]:
    async with engine.connect() as connection:
        return [tuple(row) for row in await connection.execute(POLICIES)]


@pytest.mark.postgres
async def test_migrations_keep_tenants_apart_on_postgresql(postgres: AsyncEngine) -> None:
    await migrate(postgres)
    assert len(await _policies(postgres)) == len(metadata.tables)
    async with postgres.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0003"))
    assert await _policies(postgres) == []
    assert not any(await _row_security(postgres)), "every table's row-level security is off"


@pytest.mark.postgres
async def test_create_schema_keeps_tenants_apart_as_the_migrations_do(
    postgres: AsyncEngine, tmp_path: Path
) -> None:
    await migrate(postgres)
    async with empty_database("postgres", tmp_path) as other:
        await create_schema(other)
        assert await _policies(other) == await _policies(postgres)
