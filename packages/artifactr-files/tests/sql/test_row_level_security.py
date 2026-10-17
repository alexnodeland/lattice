"""Row-level security: PostgreSQL keeps tenants apart by itself.

With the stores' own scoping bypassed, by reading the tables directly, a role the policies hold
sees only its transaction's tenant's rows, writes only its own, and sees nothing in a
transaction that names no tenant.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from artifactr.core import UserActor
from artifactr.workspace import Scope
from artifactr_files.blobs import once
from artifactr_files.checkouts import Checkout
from artifactr_files.manifest import DOCX
from artifactr_files.sql import SqlBlobs, SqlCheckouts, migrate
from lattice_core.sql.tenancy import TENANT_KEY, TenantSession
from tests.databases import empty_database, row_level_security
from tests.files_of import digest

TABLES = ("artifactr_files_blobs", "artifactr_files_checkouts")


@pytest.fixture
async def engines() -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """The owner's engine and the application's, with a blob and a check-out in each tenant."""
    async with row_level_security() as (owner, application):
        blobs = SqlBlobs(application, row_level_security=True)
        checkouts = SqlCheckouts(application, row_level_security=True)
        for tenant in ("acme", "globex"):
            scope = Scope(tenant, "w1")
            await blobs.put(scope, "a1", once(tenant.encode()), DOCX)
            checkout = Checkout(
                id="co_1",
                artifact_id="a1",
                base_version=1,
                base_sha256=digest(tenant),
                actor=UserActor(id="alice"),
                expires_at=datetime(2026, 10, 17, tzinfo=UTC),
            )
            await checkouts.save(scope, checkout)
        yield owner, application


@pytest.mark.postgres
@pytest.mark.parametrize("table", TABLES)
async def test_a_tenant_sees_only_its_rows(
    engines: tuple[AsyncEngine, AsyncEngine], table: str
) -> None:
    owner, application = engines
    tenants = text(f"SELECT DISTINCT tenant_id FROM {table}")
    sessions = async_sessionmaker(application, sync_session_class=TenantSession)
    for tenant in ("acme", "globex"):
        async with sessions(info={TENANT_KEY: tenant}) as session, session.begin():
            assert list(await session.scalars(tenants)) == [tenant]
    async with application.connect() as connection:
        assert list(await connection.scalars(tenants)) == [], "no tenant, no rows"
    async with owner.connect() as connection:
        assert len(list(await connection.scalars(tenants))) == 2, "the owner sees every row"


@pytest.mark.postgres
async def test_a_tenant_writes_only_its_rows(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    _, application = engines
    sessions = async_sessionmaker(application, sync_session_class=TenantSession)
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with sessions(info={TENANT_KEY: "acme"}) as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO artifactr_files_blobs"
                    " (tenant_id, workspace_id, artifact_id, sha256, size, data, last_put)"
                    " VALUES ('globex', 'w1', 'a2', 'x', 0, '', now())"
                )
            )
    async with sessions(info={TENANT_KEY: "acme"}) as session, session.begin():
        connection = await session.connection()
        deleted = await connection.execute(
            text("DELETE FROM artifactr_files_blobs WHERE tenant_id = 'globex'")
        )
        assert deleted.rowcount == 0


async def test_sqlite_takes_the_option_and_has_nothing_to_set(tmp_path: Path) -> None:
    async with empty_database("sqlite", tmp_path) as engine:
        await migrate(engine, application_role="application")  # nothing to grant
        blobs = SqlBlobs(engine, row_level_security=True)
        put = await blobs.put(Scope("acme", "w1"), "a1", once(b"acme's"), DOCX)
        assert await blobs.get(Scope("acme", "w1"), "a1", put.sha256) == b"acme's"
        checkouts = SqlCheckouts(engine, row_level_security=True)
        assert await checkouts.get(Scope("acme", "w1"), "co_1") is None
