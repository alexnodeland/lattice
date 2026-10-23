"""A database at the schema each package's last release left it, migrated to this commit's:
artifactr from 0.2.1, grantr from 0.1.0, relayr from 0.1.1.

For artifactr, grantr and relayr, the packages whose 0.2 adds migrations, the database is migrated
to the revision their last release's head was, a row is written in every table it had then, and
then the package's own `migrate` runs, as an application does when it starts on the new release.
Each row must still be there, column for column, and the schema must be the models'.

The rows are written from the schema as it was, a value for each column by its type, rather than
by the old release's own code: what is held is that the migrations keep what was there, not that
0.1's code wrote it. On SQLite always, and on PostgreSQL where `<PACKAGE>_TEST_POSTGRES_URL`
names a database, as CI's Check job does: each in a schema of its own, dropped as it ends. On
PostgreSQL every table of the package's must also have row-level security on, with its policies,
the new ones included.
"""

import asyncio
import contextlib
import datetime
import os
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    JSON,
    Boolean,
    Connection,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    insert,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import artifactr.sql.schema as artifactr_schema
import grantr.sql.schema as grantr_schema
import relayr.sql.schema as relayr_schema
from artifactr.files.sql import migrate as migrate_files
from artifactr.files.sql.tables import metadata as files_metadata
from artifactr.sql import migrate as migrate_artifactr
from artifactr.sql.tables import VERSION_TABLE as ARTIFACTR_VERSIONS
from artifactr.sql.tables import metadata as artifactr_metadata
from grantr.sql import migrate as migrate_grantr
from grantr.sql.tables import VERSION_TABLE as GRANTR_VERSIONS
from grantr.sql.tables import metadata as grantr_metadata
from relayr.sql import migrate as migrate_relayr
from relayr.sql.tables import VERSION_TABLE as RELAYR_VERSIONS
from relayr.sql.tables import metadata as relayr_metadata

Migrate = Callable[[AsyncEngine], Any]

RELEASED: Mapping[str, tuple[Callable[[Connection], Config], str, Migrate, MetaData, str]] = {
    # artifactr-v0.2.1, not a 0.1 release: the core's head was 0006, which is still its head, so
    # its upgrade adds nothing to the core's tables; what it holds is that native files' schema,
    # new in 0.2, is made beside them and leaves their rows alone.
    "artifactr": (
        artifactr_schema._alembic_config,
        "0006",
        migrate_artifactr,
        artifactr_metadata,
        ARTIFACTR_VERSIONS,
    ),
    # grantr-v0.1.0: 0005, before 0006's integrations.
    "grantr": (
        grantr_schema._alembic_config,
        "0005",
        migrate_grantr,
        grantr_metadata,
        GRANTR_VERSIONS,
    ),
    # relayr-v0.1.1: 0004, before 0005 to 0007's trackers.
    "relayr": (
        relayr_schema._alembic_config,
        "0004",
        migrate_relayr,
        relayr_metadata,
        RELAYR_VERSIONS,
    ),
}
"""Each package: its migrations, its last release's head, its migrate, its models and versions."""

NOW = datetime.datetime(2026, 10, 1, 12, tzinfo=datetime.UTC)


def value_of(column: Any) -> Any:
    """A value of the column's type, which every one of its checks accepts."""
    kind = column.type
    if isinstance(kind, Boolean):
        return True
    if isinstance(kind, Integer):
        return 1
    if isinstance(kind, DateTime):
        return NOW
    if isinstance(kind, JSON):
        return {}
    if isinstance(kind, LargeBinary):
        return b"0.1"
    if isinstance(kind, String | Text):
        return "v01"
    raise AssertionError(f"no value for {column.table.name}.{column.name}'s {kind!r}")


def seeded(connection: Connection, versions: str) -> dict[str, dict[str, Any]]:
    """Write one row in each of the package's tables, as they are now; return them by table."""
    reflected = MetaData()
    reflected.reflect(connection)
    rows: dict[str, dict[str, Any]] = {}
    for table in reflected.sorted_tables:
        if table.name == versions:
            continue
        row = {column.name: value_of(column) for column in table.columns}
        connection.execute(insert(table).values(row))
        rows[table.name] = row
    return rows


def kept(connection: Connection, rows: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Each seeded row's columns that are no longer as they were, by table."""
    changed: dict[str, list[str]] = {}
    for name, row in rows.items():
        table = Table(name, MetaData(), autoload_with=connection)
        found = connection.execute(select(*(table.c[c] for c in row))).mappings().all()
        if len(found) != 1:
            changed[name] = [f"{len(found)} rows"]
            continue
        differ = [c for c, v in row.items() if _same(found[0][c]) != _same(v)]
        if differ:
            changed[name] = differ
    return changed


def _same(value: Any) -> Any:
    """A value as either database gives it back: a datetime without its zone."""
    return value.replace(tzinfo=None) if isinstance(value, datetime.datetime) else value


def unguarded(connection: Connection, tables: list[str]) -> list[str]:
    """The tables, of those named, without row-level security on, or with no policy."""
    guarded = set(
        connection.scalars(
            text(
                "SELECT c.relname FROM pg_class c"
                " WHERE c.relnamespace = current_schema()::regnamespace AND c.relrowsecurity"
                " AND EXISTS (SELECT 1 FROM pg_policies p"
                " WHERE p.schemaname = current_schema() AND p.tablename = c.relname)"
            )
        )
    )
    return sorted(set(tables) - guarded)


def schema_differences(connection: Connection, models: list[MetaData]) -> list[Any]:
    """How the database's tables differ from the models', its migrations' versions aside."""

    def ours(name: str | None, kind: str, _: Mapping[str, Any]) -> bool:
        return not (kind == "table" and name is not None and name.endswith("alembic_version"))

    together = MetaData()  # alembic compares one MetaData: the models' tables, all in one
    for metadata in models:
        for table in metadata.tables.values():
            table.to_metadata(together)
    context = MigrationContext.configure(connection, opts={"include_name": ours})
    return compare_metadata(context, together)


def _postgres(package: str) -> str | None:
    """The package's PostgreSQL test database, if one is named.

    CI's Check job names one for each package, which runs these; a job that names none, as the
    Tests jobs, skips them. One that names some and not others is a mistake, and fails.
    """
    named = {name: os.environ.get(f"{name.upper()}_TEST_POSTGRES_URL") for name in RELEASED}
    if any(named.values()) and not all(named.values()):
        missing = sorted(
            f"{name.upper()}_TEST_POSTGRES_URL" for name, url in named.items() if not url
        )
        pytest.fail(f"PostgreSQL is named for some packages and not {', '.join(missing)}")
    return named[package]


def _url(backend: str, package: str, tmp_path: Path) -> str | None:
    """The backend's database for the package: a SQLite file, or PostgreSQL's if one is named."""
    if backend == "sqlite":
        return f"sqlite+aiosqlite:///{tmp_path / 'released.db'}"
    return _postgres(package)


@contextlib.asynccontextmanager
async def _engine(url: str) -> AsyncIterator[AsyncEngine]:
    """An empty database: the SQLite file named, or a PostgreSQL schema of its own."""
    if url.startswith("sqlite"):
        engine = create_async_engine(url)
        try:
            yield engine
        finally:
            await engine.dispose()
        return
    schema = f"upgrade_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(url)
    try:
        async with admin.begin() as connection:
            await connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        try:
            yield engine
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    finally:
        await admin.dispose()


async def _upgrade_keeps_the_rows(engine: AsyncEngine, package: str) -> None:
    config, head, migrate, metadata, versions = RELEASED[package]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(config(c), head))
        rows = await connection.run_sync(seeded, versions)
    assert rows, f"{package}'s release had tables"

    # What an application on the new release does as it starts.
    await migrate(engine)
    if package == "artifactr":
        await migrate_files(engine)  # native files' schema, new in 0.2, beside the core's

    models = [metadata, files_metadata] if package == "artifactr" else [metadata]
    async with engine.connect() as connection:
        assert await connection.run_sync(kept, rows) == {}, f"{package}'s rows changed"
        differences = await connection.run_sync(schema_differences, models)
        assert differences == [], f"{package}'s schema is the models'"
        if engine.dialect.name == "postgresql":
            tables = [name for model in models for name in model.tables]
            assert await connection.run_sync(unguarded, tables) == [], "row-level security"


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
@pytest.mark.parametrize("package", list(RELEASED))
def test_a_database_at_the_last_release_keeps_its_rows_on_upgrade(
    tmp_path: Path, backend: str, package: str
) -> None:
    url = _url(backend, package, tmp_path)
    if url is None:
        pytest.skip(f"no {package.upper()}_TEST_POSTGRES_URL")

    async def run() -> None:
        async with _engine(url) as engine:
            await _upgrade_keeps_the_rows(engine, package)

    asyncio.run(run())


def test_postgresql_named_for_some_packages_and_not_others_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in RELEASED:
        monkeypatch.delenv(f"{name.upper()}_TEST_POSTGRES_URL", raising=False)
    assert _postgres("grantr") is None, "none named: skipped"
    monkeypatch.setenv("GRANTR_TEST_POSTGRES_URL", "postgresql+asyncpg://localhost/grantr")
    with pytest.raises(pytest.fail.Exception, match="ARTIFACTR_TEST_POSTGRES_URL"):
        _postgres("grantr")
