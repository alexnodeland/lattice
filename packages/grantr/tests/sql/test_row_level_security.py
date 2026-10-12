"""Row-level security (lattice RFC-0001's phase 6): PostgreSQL keeps tenants apart by itself.

With grantr's own scoping bypassed, by reading the tables directly, a role the policies hold sees
only its transaction's tenant's rows, and the deployment's; it writes only its own, and sees
nothing in a transaction that names no tenant.
"""

import ast
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from grantr.core import User
from grantr.grants import Grants
from grantr.sql import SqlStorage, migrate, storage
from grantr.sql.storage import ACROSS_TENANTS
from grantr.sql.tenancy import TENANT, TenantSession
from tests.catalogs import ARTIFACTR
from tests.databases import empty_database, row_level_security

GRANTS = text("SELECT DISTINCT tenant_id FROM grantr_grants ORDER BY tenant_id")
KEYS = text("SELECT tenant_id FROM grantr_keys")
DEPLOYMENTS_AUDIT = text("SELECT seq FROM grantr_audit WHERE tenant_id = '~deployment'")
DEPLOYMENTS_KEY = text(
    "INSERT INTO grantr_keys (id, tenant_id, principal_id, digest)"
    " VALUES ('k1', '~deployment', 'ops', 'x')"
)
DELETE_DEPLOYMENTS = text("DELETE FROM grantr_grants WHERE tenant_id = '~deployment'")
UPDATE_DEPLOYMENTS = text("UPDATE grantr_grants SET role = 'x' WHERE tenant_id = '~deployment'")
MOVE_GRANTS = text("UPDATE grantr_grants SET tenant_id = 'globex' WHERE tenant_id = 'acme'")
ANOTHERS = text("INSERT INTO grantr_roles (tenant_id, name, actions) VALUES ('globex', 'x', '[]')")


@asynccontextmanager
async def _session(engine: AsyncEngine, tenant: str) -> AsyncIterator[AsyncSession]:
    """A transaction in a tenant, as the storage begins one."""
    sessions = async_sessionmaker(engine, sync_session_class=TenantSession)
    async with sessions(info={TENANT: tenant}) as session, session.begin():
        yield session


@pytest.fixture
async def engines() -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """The owner's engine and the application's, with acme and globex in grantr."""
    async with row_level_security() as (owner, application):
        storage = SqlStorage(application, row_level_security=True, across_tenants=owner)
        grants = Grants(storage, catalogs=[ARTIFACTR])
        await grants.first_operator("root")
        for tenant in ("acme", "globex"):
            await grants.create_tenant(tenant, owner=f"{tenant}-owner", by=User(id="root"))
        yield owner, application


@pytest.mark.postgres
async def test_a_tenant_sees_only_its_rows_and_the_deployments_grants(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = engines
    async with owner.begin() as connection:
        await connection.execute(DEPLOYMENTS_KEY)
    for tenant in ("acme", "globex"):
        async with _session(application, tenant) as session:
            assert set(await session.scalars(GRANTS)) == {tenant, "~deployment"}
            assert list(await session.scalars(DEPLOYMENTS_AUDIT)) == [], "only its grants"
            assert list(await session.scalars(KEYS)) == [], "no one's keys but its own"
    async with application.connect() as connection:
        assert list(await connection.scalars(GRANTS)) == [], "no tenant, no rows"
        await connection.execute(text("SELECT set_config('lattice.tenant_id', '', false)"))
        assert list(await connection.scalars(GRANTS)) == [], "an empty tenant, no rows"
    async with owner.connect() as connection:
        assert len(list(await connection.scalars(GRANTS))) == 3, "the owner sees every row"


@pytest.mark.postgres
async def test_a_tenant_changes_nothing_of_the_deployments(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = engines
    async with _session(application, "acme") as session:
        connection = await session.connection()
        assert (await connection.execute(DELETE_DEPLOYMENTS)).rowcount == 0
        assert (await connection.execute(UPDATE_DEPLOYMENTS)).rowcount == 0
    async with owner.connect() as connection:
        assert "~deployment" in set(await connection.scalars(GRANTS)), "the grants remain"


@pytest.mark.postgres
async def test_a_tenant_moves_no_row_to_another(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    _, application = engines
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with _session(application, "acme") as session:
            await session.execute(MOVE_GRANTS)


@pytest.mark.postgres
async def test_a_tenant_writes_only_its_rows(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    _, application = engines
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with _session(application, "acme") as session:
            await session.execute(ANOTHERS)


async def test_a_session_must_name_its_tenant(tmp_path: Path) -> None:
    async with empty_database("sqlite", tmp_path) as engine:
        sessions = async_sessionmaker(engine, sync_session_class=TenantSession)
        with pytest.raises(RuntimeError, match="must name its tenant"):
            async with sessions() as session, session.begin():
                await session.execute(text("SELECT 1"))


async def test_sqlite_takes_the_option_and_has_nothing_to_set(tmp_path: Path) -> None:
    async with empty_database("sqlite", tmp_path) as engine:
        await migrate(engine, application_role="application")  # nothing to grant
        with pytest.raises(ValueError, match="reads across tenants"):
            SqlStorage(engine, row_level_security=True)
        storage = SqlStorage(engine, row_level_security=True, across_tenants=engine)
        grants = Grants(storage, catalogs=[ARTIFACTR])
        await grants.first_operator("root")
        await grants.create_tenant("acme", owner="alice", by=User(id="root"))
        assert await grants.tenants(by=User(id="root")) == ["acme"]


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
                else:
                    using.add(function.name)
    assert using == ACROSS_TENANTS


def _names_across(node: ast.AST) -> bool:
    """Whether a node names the engine across tenants, as an attribute or through getattr."""
    if isinstance(node, ast.Attribute):
        return node.attr == "_across"
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "setattr"}
        and any(isinstance(arg, ast.Constant) and arg.value == "_across" for arg in node.args)
    )
