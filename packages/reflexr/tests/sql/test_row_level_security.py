"""Row-level security (lattice RFC-0001's phase 6): PostgreSQL keeps tenants apart by itself.

With reflexr's own scoping bypassed, by reading the tables directly, a role the policies hold
sees only its transaction's tenant's rows, writes only its own, and sees nothing in a
transaction that names no tenant. The dispatcher's and the scheduler's reads across tenants
use the other engine, and nothing else does.
"""

import ast
import inspect
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from reflexr.sql import SqlStorage, migrate, storage
from reflexr.sql.storage import ACROSS_TENANTS
from reflexr.sql.tenancy import TENANT, TenantSession, grant
from reflexr.workspace import WorkspaceRef
from tests.databases import APPLICATION_ROLE, empty_database, row_level_security

AT = datetime(2026, 10, 12, tzinfo=UTC)
SCHEDULES = text("SELECT DISTINCT tenant_id FROM reflexr_schedules")
DELETE_GLOBEXS = text("DELETE FROM reflexr_schedules WHERE tenant_id = 'globex'")
UPDATE_GLOBEXS = text("UPDATE reflexr_workspaces SET head_seq = 0 WHERE tenant_id = 'globex'")
MOVE_ACMES = text("UPDATE reflexr_schedules SET tenant_id = 'globex' WHERE tenant_id = 'acme'")
ANOTHERS = text(
    "INSERT INTO reflexr_cursors (tenant_id, workspace_id, name, seq)"
    " VALUES ('globex', 'w1', 'c', 1)"
)


async def _schedule(storage: SqlStorage, *tenants: str) -> None:
    for tenant in tenants:
        async with storage.transaction(WorkspaceRef(tenant, "w1")) as transaction:
            await transaction.save_schedule("nightly", AT)


@pytest.fixture
async def engines() -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """The owner's engine and the application's, with a schedule in acme and globex."""
    async with row_level_security() as (owner, application):
        storage = SqlStorage(application, row_level_security=True, across_tenants=owner)
        await _schedule(storage, "acme", "globex")
        yield owner, application


@pytest.mark.postgres
async def test_a_tenant_sees_only_its_rows(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    owner, application = engines
    sessions = async_sessionmaker(application, sync_session_class=TenantSession)
    for tenant in ("acme", "globex"):
        async with sessions(info={TENANT: tenant}) as session, session.begin():
            assert list(await session.scalars(SCHEDULES)) == [tenant]
    async with application.connect() as connection:
        assert list(await connection.scalars(SCHEDULES)) == [], "no tenant, no rows"
    async with owner.connect() as connection:
        assert len(list(await connection.scalars(SCHEDULES))) == 2, "the owner sees every row"


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
        assert set(await connection.scalars(SCHEDULES)) == {"acme", "globex"}, "all remain"


@pytest.mark.postgres
async def test_an_empty_tenant_sees_nothing(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    _, application = engines
    async with application.connect() as connection:
        await connection.execute(text("SELECT set_config('lattice.tenant_id', '', false)"))
        assert list(await connection.scalars(SCHEDULES)) == []


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
        with pytest.raises(ValueError, match="reads across tenants"):
            SqlStorage(engine, row_level_security=True)
        storage = SqlStorage(engine, row_level_security=True, across_tenants=engine)
        await _schedule(storage, "acme")
        assert await storage.schedules(WorkspaceRef("acme", "w1")) == {"nightly": AT}


def test_only_the_reads_across_tenants_use_their_engine() -> None:
    module = ast.parse(inspect.getsource(storage))
    using: set[str] = set()
    for function in ast.walk(module):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(function):
            if _names_across(node):
                assert isinstance(node, ast.Attribute)
                if isinstance(node.ctx, ast.Store):
                    assert function.name == "__init__", "only the constructor sets it"
                elif function.name != "_across_all":
                    using.add(function.name)
    assert using == ACROSS_TENANTS


def _names_across(node: ast.AST) -> bool:
    """Whether a node names the engine across tenants, or the read that uses it."""
    names = {"_across", "_across_all"}
    if isinstance(node, ast.Attribute):
        return node.attr in names
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "setattr"}
        and any(isinstance(arg, ast.Constant) and arg.value in names for arg in node.args)
    )
