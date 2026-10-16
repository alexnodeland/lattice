"""The packaged migrations build exactly the schema the models describe."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import JSON, Connection, column, inspect, table, text
from sqlalchemy.ext.asyncio import AsyncEngine

from grantr.sql import create_schema, migrate
from grantr.sql.schema import DEPLOYMENT_READS, TENANT_COLUMNS, _alembic_config
from grantr.sql.tables import VERSION_TABLE, metadata
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
    assert len(await _policies(postgres)) == len(TENANT_COLUMNS) + len(DEPLOYMENT_READS) + 1
    async with postgres.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0002"))
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


def _entry(tenant: str, by: dict[str, str] | None, type: str) -> dict[str, Any]:
    at = "2026-10-12T00:00:00+00:00"
    return {"tenant_id": tenant, "body": {"at": at, "by": by, "event": {"type": type}}}


async def test_the_audit_filters_migration_fills_each_entrys_type_and_maker(
    engine: AsyncEngine,
) -> None:
    """Entries made before 0004 get their event's type and their maker's columns, and a
    downgrade with entries present takes the columns away again."""
    rule = {"kind": "rule", "workspace": "team/notes", "rule": "chat:x"}
    entries = [
        _entry("~deployment", None, "granted"),
        _entry("acme", {"kind": "user", "id": "alice"}, "member_added"),
        _entry("acme", {"kind": "service_principal", "id": "app"}, "restricted"),
        _entry("acme", rule, "granted"),
        _entry("acme", {"kind": "agent"}, "revoked"),
    ]
    audit = table("grantr_audit", column("tenant_id"), column("body", JSON()))
    columns = "event_type, actor_kind, actor_workspace, actor_id"
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0003"))
        await connection.execute(audit.insert(), entries)
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "head"))
        filled = await connection.execute(text(f"SELECT {columns} FROM grantr_audit ORDER BY seq"))
        assert [tuple(row) for row in filled] == [
            ("granted", "", "", ""),
            ("member_added", "user", "", "alice"),
            ("restricted", "service_principal", "", "app"),
            ("granted", "rule", "team/notes", "chat:x"),
            ("revoked", "agent", "", ""),
        ]
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0003"))
        kept = await connection.execute(text("SELECT body FROM grantr_audit ORDER BY seq"))
        assert len(kept.all()) == len(entries)
        assert "actor_kind" not in {
            each["name"]
            for each in await connection.run_sync(lambda c: inspect(c).get_columns("grantr_audit"))
        }


async def test_the_audit_filters_migration_refuses_a_maker_of_no_known_kind(
    engine: AsyncEngine,
) -> None:
    audit = table("grantr_audit", column("tenant_id"), column("body", JSON()))
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0003"))
        await connection.execute(audit.insert(), [_entry("acme", {"kind": "group"}, "granted")])
        with pytest.raises(ValueError, match="no known kind"):
            await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "head"))
