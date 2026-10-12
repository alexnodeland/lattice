"""Creating and upgrading relayr's tables.

The Alembic migrations ship inside this package and record their version in their own table
(`relayr_alembic_version`), so they run beside an application's own migrations, and the
libraries', in the same database.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from relayr.sql.tables import metadata
from relayr.sql.tenancy import grant, tenant_policy


async def migrate(engine: AsyncEngine, *, application_role: str | None = None) -> None:
    """Upgrade the database to relayr's latest schema, creating the tables if needed.

    Run it when the application deploys or starts, as the tables' owner. It is safe to run on
    every start: a database that is already up to date is left alone.

    Args:
        engine: The database, as the tables' owner.
        application_role: A role that owns nothing, which the application connects as with
            row-level security on: it is granted relayr's tables, on PostgreSQL. It must exist.
    """
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
        if application_role is not None:
            await connection.run_sync(grant, application_role, list(metadata.tables))


async def create_schema(engine: AsyncEngine) -> None:
    """Create relayr's tables straight from the models, for tests and prototypes.

    It skips Alembic, so the database records no schema version and cannot be upgraded with
    [`migrate`][relayr.sql.migrate] later. Use `migrate` for databases that last.
    """
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.run_sync(_row_level_security)


def _alembic_config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", "relayr.sql:migrations")
    config.attributes["connection"] = connection
    return config


def _upgrade(connection: Connection) -> None:
    command.upgrade(_alembic_config(connection), "head")


def _row_level_security(connection: Connection) -> None:
    """Create the policies the migrations create, on PostgreSQL.

    Each table keeps its rows to their tenant.
    """
    if connection.dialect.name != "postgresql":
        return
    for table in metadata.tables:
        for statement in tenant_policy(table):
            connection.execute(text(statement))
