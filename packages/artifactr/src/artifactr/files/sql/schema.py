"""Creating and upgrading the native files' tables.

The Alembic migrations ship inside this package and record their version in their own table
(`artifactr_files_alembic_version`), so they run beside artifactr's storage migrations, an
application's own and the other libraries', in the same database.
"""

from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from artifactr.files.sql.tables import metadata
from lattice_core.sql.tenancy import grant, tenant_policy

EXTERNAL: Final = "ALTER TABLE artifactr_files_blobs ALTER COLUMN data SET STORAGE EXTERNAL"
"""Blobs are stored out of line and uncompressed on PostgreSQL: zipped formats don't compress."""


async def migrate(engine: AsyncEngine, *, application_role: str | None = None) -> None:
    """Upgrade the database to the native files' latest schema, creating the tables if needed.

    Run it when the application deploys or starts, as the tables' owner. It is safe to run on
    every start: a database that is already up to date is left alone.

    Args:
        engine: The database, as the tables' owner.
        application_role: A role that owns nothing, which the application connects as with
            row-level security on: it is granted the tables, on PostgreSQL. It must exist.
    """
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
        if application_role is not None:
            await connection.run_sync(grant, application_role, list(metadata.tables))


async def create_schema(engine: AsyncEngine) -> None:
    """Create the tables straight from the models, for tests and prototypes.

    It skips Alembic, so the database records no schema version and cannot be upgraded with
    [`migrate`][artifactr.files.sql.migrate] later. Use `migrate` for databases that last.
    """
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.run_sync(_on_postgresql)


def _alembic_config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", "artifactr.files.sql:migrations")
    config.attributes["connection"] = connection
    return config


def _upgrade(connection: Connection) -> None:
    command.upgrade(_alembic_config(connection), "head")


def _on_postgresql(connection: Connection) -> None:
    """Ask PostgreSQL for what the migrations do: blobs' storage, and row-level security."""
    if connection.dialect.name != "postgresql":
        return
    connection.execute(text(EXTERNAL))
    for table in metadata.tables:
        for statement in tenant_policy(table):
            connection.execute(text(statement))
