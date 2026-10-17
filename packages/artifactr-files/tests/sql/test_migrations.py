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

from artifactr_files.sql import create_schema, migrate
from artifactr_files.sql.schema import _alembic_config
from artifactr_files.sql.tables import VERSION_TABLE, metadata
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
    "SELECT relname, relrowsecurity FROM pg_class"
    " WHERE relnamespace = current_schema()::regnamespace AND relkind = 'r' ORDER BY relname"
)
POLICIES = text(
    "SELECT policyname, cmd, qual, with_check FROM pg_policies"
    " WHERE schemaname = current_schema() ORDER BY policyname"
)
STORAGE = text(
    "SELECT attstorage FROM pg_attribute"
    " WHERE attrelid = 'artifactr_files_blobs'::regclass AND attname = 'data'"
)


@pytest.fixture
async def postgres(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    async with empty_database("postgres", tmp_path) as engine:
        yield engine


async def _postgresql(engine: AsyncEngine) -> tuple[list[Any], list[Any], bytes | None]:
    """What PostgreSQL alone was asked for: row-level security, the policies, blobs' storage."""
    async with engine.connect() as connection:
        secured = [tuple(row) for row in await connection.execute(ROW_SECURITY)]
        policies = [tuple(row) for row in await connection.execute(POLICIES)]
        return secured, policies, await connection.scalar(STORAGE)


@pytest.mark.postgres
async def test_migrations_keep_tenants_apart_and_blobs_uncompressed(postgres: AsyncEngine) -> None:
    await migrate(postgres)
    secured, policies, storage = await _postgresql(postgres)
    assert all(on for name, on in secured if name != VERSION_TABLE)
    assert len(policies) == len(metadata.tables)
    assert storage == b"e", "EXTERNAL: out of line, never compressed"


@pytest.mark.postgres
async def test_create_schema_asks_postgresql_what_the_migrations_do(
    postgres: AsyncEngine, tmp_path: Path
) -> None:
    await migrate(postgres)
    async with empty_database("postgres", tmp_path) as other:
        await create_schema(other)
        migrated, created = await _postgresql(postgres), await _postgresql(other)
        assert migrated[1:] == created[1:]
        assert [row for row in migrated[0] if row[0] != VERSION_TABLE] == created[0]
