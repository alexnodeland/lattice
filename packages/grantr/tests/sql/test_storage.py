"""What the SQL adapter adds to the contract: its keys, its locks, and awaiting every call."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from grantr.core import (
    DEPLOYMENT,
    TENANT,
    Agent,
    AuditFilter,
    Forbidden,
    Grant,
    Grantee,
    Group,
    Resource,
    RulePrincipal,
    ServicePrincipal,
    User,
)
from grantr.grants import Grants
from grantr.sql import SqlStorage, create_schema, create_sqlite_engine
from grantr.sql.storage import (
    Columns,
    _scope,
    audit_query,
    grantee,
    resource,
    resource_columns,
    subject_columns,
)
from grantr.sql.tables import TenantRow
from tests.databases import empty_database


@pytest.mark.parametrize(
    ("subject", "columns"),
    [
        (User(id="a:b"), ("user", "", "a:b")),
        (ServicePrincipal(id="ci"), ("service_principal", "", "ci")),
        (RulePrincipal(workspace="w1", rule="ops:page"), ("rule", "w1", "ops:page")),
        (Group(id="team"), ("group", "", "team")),
    ],
)
def test_a_subject_is_stored_in_its_columns(subject: Grantee, columns: Columns) -> None:
    assert subject_columns(subject) == columns
    assert grantee(*columns) == subject


@pytest.mark.parametrize(
    ("on", "columns"),
    [
        (DEPLOYMENT, ("deployment", "", "")),
        (TENANT, ("tenant", "", "")),
        (Resource(kind="workspace", workspace="w1"), ("workspace", "w1", "")),
        (Resource(kind="rule", workspace="w1", id="ops:page"), ("rule", "w1", "ops:page")),
    ],
)
def test_a_resource_is_stored_in_its_columns(on: Resource, columns: Columns) -> None:
    assert resource_columns(on) == columns
    assert resource(*columns) == on


@pytest.mark.parametrize("tenant", ["", "~deployment", "a~b"])
def test_no_tenant_is_stored_as_the_deployment(tenant: str) -> None:
    with pytest.raises(ValueError, match="isn't a tenant id"):
        _scope(tenant)


async def test_a_refused_command_leaves_no_row(engine: AsyncEngine) -> None:
    await create_schema(engine)
    grants = Grants(SqlStorage(engine))
    with pytest.raises(Forbidden):
        await grants.create_tenant("acme", owner="alice", by=Agent())
    async with engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(TenantRow)) == 0


async def test_an_engine_can_pool_connections_its_own_way(tmp_path: Path) -> None:
    engine = create_sqlite_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'grantr.db'}", poolclass=NullPool
    )
    try:
        assert isinstance(engine.pool, NullPool)
        await create_schema(engine)
        grants = Grants(SqlStorage(engine))
        await grants.first_operator("root")
        await grants.create_tenant("acme", owner="alice", by=User(id="root"))
        assert await grants.member("acme", "alice") is not None
    finally:
        await engine.dispose()


VIEWER = Grant(tenant="acme", role="viewer", on=TENANT, to=User(id="bob"))


@pytest.mark.parametrize("tenant", ["new", "existing"])
async def test_a_transaction_waits_for_the_one_before_it(engine: AsyncEngine, tenant: str) -> None:
    await create_schema(engine)
    first, second = SqlStorage(engine), SqlStorage(engine)
    if tenant == "existing":
        async with first.transaction("acme") as tx:
            await tx.create_tenant("acme")
    began, release = asyncio.Event(), asyncio.Event()

    async def grant_when_released() -> None:
        async with first.transaction("acme") as tx:
            began.set()
            await release.wait()
            await tx.add_grant(VIEWER)

    async def look() -> bool:
        async with second.transaction("acme") as tx:
            return await tx.has(VIEWER)

    granter = asyncio.create_task(grant_when_released())
    await began.wait()
    looker = asyncio.create_task(look())
    await asyncio.sleep(0.2)
    assert not looker.done(), "the second transaction waits for the first to end"
    release.set()
    await granter
    assert await asyncio.wait_for(looker, timeout=5), "and then sees its change"


async def test_a_tenants_concurrent_changes_are_numbered_in_order(engine: AsyncEngine) -> None:
    await create_schema(engine)
    root = User(id="root")
    setup = Grants(SqlStorage(engine))
    await setup.first_operator(root.id)
    await setup.create_tenant("acme", owner="alice", by=root)
    handles = [Grants(SqlStorage(engine)) for _ in range(4)]
    await asyncio.gather(
        *(
            grants.add_member("acme", User(id=f"user{i}"), by=User(id="alice"))
            for i, grants in enumerate(handles * 3)
        )
    )
    entries = await setup.audit("acme", by=User(id="alice"))
    assert [entry.seq for entry in entries] == list(range(2, 15))


async def test_one_of_two_concurrent_creations_of_a_tenant_wins(engine: AsyncEngine) -> None:
    await create_schema(engine)
    root = User(id="root")
    await Grants(SqlStorage(engine)).first_operator(root.id)
    attempts = [
        Grants(SqlStorage(engine)).create_tenant("x", owner=owner, by=root)
        for owner in ("alice", "bob")
    ]
    results = await asyncio.gather(*attempts, return_exceptions=True)
    assert sorted(type(result).__name__ for result in results) == ["AuditEntry", "Invalid"]


@pytest.mark.postgres
@pytest.mark.parametrize(
    ("keep", "index"),
    [
        (AuditFilter(types=frozenset({"granted"})), "ix_grantr_audit_event_type"),
        (AuditFilter(by=User(id="bob")), "ix_grantr_audit_actor"),
    ],
)
async def test_a_page_back_reads_the_type_or_the_actor_index_on_postgresql(
    tmp_path: Path, keep: AuditFilter, index: str
) -> None:
    """On a long log, a page back by type or by maker is that index's range: the window's end,
    ``seq < before_seq``, keeps it so on PostgreSQL."""
    query = audit_query("acme", before_seq=4000, last=10, keep=keep)
    compiled = query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    async with empty_database("postgres", tmp_path) as engine:
        await create_schema(engine)
        async with engine.begin() as connection:
            # A tenant's long log, mostly others' members added: a granted, or bob's, is rare.
            await connection.execute(
                text(
                    "INSERT INTO grantr_audit"
                    " (tenant_id, event_type, actor_kind, actor_workspace, actor_id, body)"
                    " SELECT 'acme',"
                    " CASE WHEN n % 100 = 0 THEN 'granted' ELSE 'member_added' END,"
                    " 'user', '', CASE WHEN n % 100 = 1 THEN 'bob' ELSE 'u' || n END, '{}'"
                    " FROM generate_series(1, 5000) AS n"
                )
            )
            await connection.execute(text("ANALYZE grantr_audit"))
            plan = await connection.execute(text(f"EXPLAIN {compiled}"))
            assert index in "\n".join(row[0] for row in plan)
