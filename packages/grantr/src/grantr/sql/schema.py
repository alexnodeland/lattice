"""Creating and upgrading grantr's tables.

The Alembic migrations ship inside this package and record their version in their own table
(``grantr_alembic_version``), so they run beside an application's own migrations, and the
libraries', in the same database.
"""

from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from grantr.sql.tables import DEPLOYMENT, metadata
from grantr.sql.tenancy import CURRENT, grant, tenant_policy

TENANT_COLUMNS: Final = {
    "grantr_tenants": "id",
    "grantr_grants": "tenant_id",
    "grantr_resources": "tenant_id",
    "grantr_groups": "tenant_id",
    "grantr_group_members": "tenant_id",
    "grantr_roles": "tenant_id",
    "grantr_keys": "tenant_id",
    "grantr_audit": "tenant_id",
}
"""Each table, and the column that names its tenant."""

DEPLOYMENT_READS: Final = ("grantr_grants", "grantr_group_members")
"""The tables whose deployment rows every tenant's checks read: the operators' and the
application's grants."""


async def migrate(engine: AsyncEngine, *, application_role: str | None = None) -> None:
    """Upgrade the database to grantr's latest schema, creating the tables if needed.

    Run it when the application deploys or starts, as the tables' owner. It is safe to run on
    every start: a database that is already up to date is left alone.

    Args:
        engine: The database, as the tables' owner.
        application_role: A role that owns nothing, which the application connects as with
            row-level security on: it is granted grantr's tables, on PostgreSQL. It must exist.
    """
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
        if application_role is not None:
            await connection.run_sync(grant, application_role, list(TENANT_COLUMNS))


async def create_schema(engine: AsyncEngine) -> None:
    """Create grantr's tables straight from the models, for tests and prototypes.

    It skips Alembic, so the database records no schema version and cannot be upgraded with
    :func:`migrate` later. Use :func:`migrate` for databases that last.
    """
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
        await connection.run_sync(_row_level_security)


def _alembic_config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", "grantr.sql:migrations")
    config.attributes["connection"] = connection
    return config


def _upgrade(connection: Connection) -> None:
    command.upgrade(_alembic_config(connection), "head")


def _row_level_security(connection: Connection) -> None:
    """Create the policies the migrations create, on PostgreSQL."""
    if connection.dialect.name != "postgresql":
        return
    for statement in row_level_security():
        connection.execute(text(statement))


def row_level_security() -> list[str]:
    """The DDL of grantr's row-level security policies, as they stand.

    Each table keeps its rows to their tenant, and every tenant reads the deployment's grants
    and its groups' members, which its checks need.
    """
    statements = [
        statement
        for table, column in TENANT_COLUMNS.items()
        for statement in tenant_policy(table, column)
    ]
    statements += [
        f"CREATE POLICY {table}_deployment ON {table} FOR SELECT"
        f" USING (tenant_id = '{DEPLOYMENT}' AND {CURRENT} <> '')"
        for table in DEPLOYMENT_READS
    ]
    return statements
