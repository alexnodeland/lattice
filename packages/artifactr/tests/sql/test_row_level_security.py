"""Row-level security (lattice RFC-0001's phase 6): PostgreSQL keeps tenants apart by itself.

With artifactr's own scoping bypassed, by reading the tables directly, a role the policies hold
sees only its transaction's tenant's rows, writes only its own, and sees nothing in a
transaction that names no tenant.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from artifactr.core import CreateThread, UserActor
from artifactr.sql import SqlStorage, migrate
from artifactr.sql.tenancy import TENANT, TenantSession, grant
from artifactr.workspace import Workspaces
from tests.databases import APPLICATION_ROLE, empty_database, row_level_security

EVENTS = text("SELECT DISTINCT tenant_id FROM artifactr_events")
DELETE_GLOBEXS = text("DELETE FROM artifactr_events WHERE tenant_id = 'globex'")
UPDATE_GLOBEXS = text("UPDATE artifactr_workspaces SET head_seq = 0 WHERE tenant_id = 'globex'")
MOVE_ACMES = text("UPDATE artifactr_threads SET tenant_id = 'globex' WHERE tenant_id = 'acme'")
ANOTHERS = text(
    "INSERT INTO artifactr_cursors (tenant_id, workspace_id, name, seq)"
    " VALUES ('globex', 'w1', 'c', 1)"
)


@pytest.fixture
async def engines() -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """The owner's engine and the application's, with a thread in acme's and globex's w1."""
    async with row_level_security() as (owner, application):
        workspaces = Workspaces(SqlStorage(application, row_level_security=True))
        for tenant in ("acme", "globex"):
            ws = await workspaces.open(tenant, "w1", actor=UserActor(id="alice"))
            await ws.commit(CreateThread())
        yield owner, application


@pytest.mark.postgres
async def test_a_tenant_sees_only_its_rows(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    owner, application = engines
    sessions = async_sessionmaker(application, sync_session_class=TenantSession)
    for tenant in ("acme", "globex"):
        async with sessions(info={TENANT: tenant}) as session, session.begin():
            assert list(await session.scalars(EVENTS)) == [tenant]
    async with application.connect() as connection:
        assert list(await connection.scalars(EVENTS)) == [], "no tenant, no rows"
    async with owner.connect() as connection:
        assert len(list(await connection.scalars(EVENTS))) == 2, "the owner sees every row"


@pytest.mark.postgres
async def test_a_tenant_writes_only_its_rows(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    owner, application = engines
    sessions = async_sessionmaker(application, sync_session_class=TenantSession)
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with sessions(info={TENANT: "acme"}) as session, session.begin():
            await session.execute(ANOTHERS)
    async with sessions(info={TENANT: "acme"}) as session, session.begin():
        connection = await session.connection()
        assert (await connection.execute(DELETE_GLOBEXS)).rowcount == 0
        assert (await connection.execute(UPDATE_GLOBEXS)).rowcount == 0
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with sessions(info={TENANT: "acme"}) as session, session.begin():
            await session.execute(MOVE_ACMES)
    async with owner.connect() as connection:
        assert set(await connection.scalars(EVENTS)) == {"acme", "globex"}, "all remain"


@pytest.mark.postgres
async def test_an_empty_tenant_sees_nothing(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    _, application = engines
    async with application.connect() as connection:
        await connection.execute(text("SELECT set_config('lattice.tenant_id', '', false)"))
        assert list(await connection.scalars(EVENTS)) == []


async def test_a_session_must_name_its_tenant(tmp_path: Path) -> None:
    async with empty_database("sqlite", tmp_path) as database:
        sessions = async_sessionmaker(database.engine(), sync_session_class=TenantSession)
        with pytest.raises(RuntimeError, match="must name its tenant"):
            async with sessions() as session, session.begin():
                await session.execute(text("SELECT 1"))


async def test_sqlite_takes_the_option_and_has_nothing_to_set(tmp_path: Path) -> None:
    async with empty_database("sqlite", tmp_path) as database:
        engine = database.engine()
        await migrate(engine, application_role="application")  # nothing to grant
        workspaces = Workspaces(SqlStorage(engine, row_level_security=True))
        ws = await workspaces.open("acme", "w1", actor=UserActor(id="alice"))
        await ws.commit(CreateThread())
        assert len(await ws.threads()) == 1


@pytest.mark.postgres
async def test_a_role_is_granted_the_sequences_its_tables_own(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, _ = engines
    async with owner.begin() as connection:
        await connection.execute(text("CREATE TABLE numbered (id serial PRIMARY KEY)"))
        await connection.run_sync(grant, APPLICATION_ROLE, ["numbered"])
        sequence = await connection.scalar(text("SELECT pg_get_serial_sequence('numbered', 'id')"))
        allowed = text("SELECT has_sequence_privilege(:role, :sequence, 'USAGE')")
        assert await connection.scalar(allowed, {"role": APPLICATION_ROLE, "sequence": sequence})
