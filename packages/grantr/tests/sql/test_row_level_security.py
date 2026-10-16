"""Row-level security (lattice RFC-0001's phase 6): PostgreSQL keeps tenants apart by itself.

With grantr's own scoping bypassed, by reading the tables directly, a role the policies hold sees
only its transaction's tenant's rows, and the deployment's; it writes only its own, and sees
nothing in a transaction that names no tenant.
"""

import ast
import inspect
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from asyncpg.exceptions import FeatureNotSupportedError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
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
DEPLOYMENT_ENTRY = text(
    "INSERT INTO grantr_audit (tenant_id, event_type, actor_kind, actor_workspace, actor_id, body)"
    " VALUES ('~deployment', :event_type, 'user', '', 'root', CAST(:body AS json))"
)
DEPLOYMENTS_ENTRIES = text(
    "SELECT event_type, body #>> '{event,tenant}' FROM grantr_audit"
    " WHERE tenant_id = '~deployment' ORDER BY seq"
)
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


def _entry(event_type: str, *, tenant: str, event: str | None = None) -> dict[str, str]:
    """The parameters of a deployment audit entry of ``event_type``, whose event names a tenant."""
    body = {
        "at": "2026-10-16T00:00:00+00:00",
        "by": None,
        "event": {"type": event or event_type, "tenant": tenant, "owner": "alice"},
    }
    return {"event_type": event_type, "body": json.dumps(body)}


CREATION = "deployment_tenant_created"


@pytest.mark.postgres
async def test_a_tenant_adds_the_one_deployment_entry_of_its_own_creation(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = engines
    async with _session(application, "acme") as session:
        await session.execute(DEPLOYMENT_ENTRY, _entry(CREATION, tenant="acme"))
    async with owner.connect() as connection:
        entries = [tuple(row) for row in await connection.execute(DEPLOYMENTS_ENTRIES)]
    assert entries == [
        ("granted", None),
        (CREATION, "acme"),
        (CREATION, "globex"),
        (CREATION, "acme"),
    ], "the operator's grant, the two creations, and the one added here"


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param(_entry("granted", tenant="acme"), id="another type of deployment entry"),
        pytest.param(_entry("tenant_deleted", tenant="acme"), id="a type that edits a tenant"),
        pytest.param(_entry(CREATION, tenant="globex"), id="the creation of another tenant"),
        pytest.param(
            _entry("granted", tenant="acme", event=CREATION),
            id="a type that its event contradicts",
        ),
        pytest.param(
            _entry(CREATION, tenant="acme", event="granted"),
            id="an event that its type contradicts",
        ),
    ],
)
@pytest.mark.postgres
async def test_a_tenant_adds_no_other_deployment_entry(
    engines: tuple[AsyncEngine, AsyncEngine], entry: dict[str, str]
) -> None:
    owner, application = engines
    async with owner.connect() as connection:
        before = list(await connection.execute(DEPLOYMENTS_ENTRIES))
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with _session(application, "acme") as session:
            await session.execute(DEPLOYMENT_ENTRY, entry)
    async with owner.connect() as connection:
        assert list(await connection.execute(DEPLOYMENTS_ENTRIES)) == before


@pytest.mark.postgres
async def test_a_tenant_reads_changes_and_deletes_none_of_the_deployments_entries(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = engines
    update = text("UPDATE grantr_audit SET actor_id = 'x' WHERE tenant_id = '~deployment'")
    delete = text("DELETE FROM grantr_audit WHERE tenant_id = '~deployment'")
    async with _session(application, "acme") as session:
        await session.execute(DEPLOYMENT_ENTRY, _entry(CREATION, tenant="acme"))
        assert list(await session.scalars(DEPLOYMENTS_AUDIT)) == [], "not even its own entry"
        connection = await session.connection()
        assert (await connection.execute(update)).rowcount == 0
        assert (await connection.execute(delete)).rowcount == 0
    async with owner.connect() as connection:
        assert len(list(await connection.execute(DEPLOYMENTS_ENTRIES))) == 4, "all remain"
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with _session(application, "acme") as session:
            await session.execute(
                text(f"{DEPLOYMENT_ENTRY.text} RETURNING seq"), _entry(CREATION, tenant="acme")
            )


@pytest.mark.postgres
async def test_the_policy_is_for_insert_alone(engines: tuple[AsyncEngine, AsyncEngine]) -> None:
    owner, _ = engines
    policies = text(
        "SELECT cmd, qual IS NULL FROM pg_policies"
        " WHERE policyname = 'grantr_audit_tenant_creation' AND schemaname = current_schema()"
    )
    async with owner.connect() as connection:
        assert [tuple(row) for row in await connection.execute(policies)] == [("INSERT", True)]


async def _deployment_seq(owner: AsyncEngine) -> int:
    async with owner.connect() as connection:
        return int(
            await connection.scalar(
                text("SELECT min(seq) FROM grantr_audit WHERE tenant_id = '~deployment'")
            )
            or 0
        )


EXPLICIT = text(
    "INSERT INTO grantr_audit"
    " (seq, tenant_id, event_type, actor_kind, actor_workspace, actor_id, body)"
    " VALUES (:seq, '~deployment', :event_type, 'user', '', 'root', CAST(:body AS json))"
)


@pytest.mark.postgres
async def test_a_creation_filed_under_the_tenants_own_id_is_the_tenants_own_row(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    """The existing tenant policy lets a tenant add rows of its own, whatever their type."""
    owner, application = engines
    own = text(
        "INSERT INTO grantr_audit (tenant_id, event_type, actor_kind, actor_workspace,"
        " actor_id, body) VALUES ('acme', :event_type, 'user', '', 'root', CAST(:body AS json))"
    )
    async with _session(application, "acme") as session:
        await session.execute(own, _entry(CREATION, tenant="acme"))
        mine = text(
            "SELECT count(*) FROM grantr_audit WHERE tenant_id = 'acme' AND event_type = :t"
        )
        assert await session.scalar(mine, {"t": CREATION}) == 1, "in its own log"
    async with owner.connect() as connection:
        assert len(list(await connection.execute(DEPLOYMENTS_ENTRIES))) == 3, "not the deployment's"


@pytest.mark.postgres
async def test_a_duplicate_number_is_refused_and_reveals_only_that_it_exists(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    """A unique violation says the number is taken, whose row it is stays unread."""
    owner, application = engines
    taken = await _deployment_seq(owner)
    with pytest.raises(IntegrityError, match="duplicate key"):
        async with _session(application, "acme") as session:
            await session.execute(EXPLICIT, {"seq": taken, **_entry(CREATION, tenant="acme")})
    async with _session(application, "acme") as session:
        await session.execute(EXPLICIT, {"seq": 10_000, **_entry(CREATION, tenant="acme")})
    async with owner.connect() as connection:
        assert 10_000 in set(await connection.scalars(text("SELECT seq FROM grantr_audit")))


@pytest.mark.postgres
async def test_on_conflict_do_nothing_adds_nothing_to_a_taken_number(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = engines
    taken = await _deployment_seq(owner)
    skipping = text(f"{EXPLICIT.text} ON CONFLICT DO NOTHING")
    async with _session(application, "acme") as session:
        connection = await session.connection()
        result = await connection.execute(
            skipping, {"seq": taken, **_entry(CREATION, tenant="acme")}
        )
        assert result.rowcount == 0
    async with owner.connect() as connection:
        assert len(list(await connection.execute(DEPLOYMENTS_ENTRIES))) == 3, "nothing was added"


@pytest.mark.postgres
async def test_on_conflict_do_update_is_refused_for_the_deployments_entries(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = engines
    taken = await _deployment_seq(owner)
    updating = text(f"{EXPLICIT.text} ON CONFLICT (seq) DO UPDATE SET actor_id = 'x'")
    with pytest.raises(ProgrammingError, match="row-level security"):
        async with _session(application, "acme") as session:
            await session.execute(updating, {"seq": taken, **_entry(CREATION, tenant="acme")})
    async with owner.connect() as connection:
        actors = set(
            await connection.scalars(
                text("SELECT actor_id FROM grantr_audit WHERE tenant_id = '~deployment'")
            )
        )
        assert "x" not in actors


COLUMNS = ["tenant_id", "event_type", "actor_kind", "actor_workspace", "actor_id", "body"]


async def _copy(application: AsyncEngine, records: list[tuple[str, ...]]) -> None:
    async with _session(application, "acme") as session:
        raw = (await (await session.connection()).get_raw_connection()).driver_connection
        assert raw is not None
        await raw.copy_records_to_table("grantr_audit", records=records, columns=COLUMNS)


def _record(entry: dict[str, str]) -> tuple[str, ...]:
    return ("~deployment", entry["event_type"], "user", "", "root", entry["body"])


@pytest.mark.postgres
async def test_copy_from_is_refused_outright_under_row_level_security(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    """PostgreSQL does not run ``COPY FROM`` into a table with policies, so it adds nothing."""
    owner, application = engines
    with pytest.raises(FeatureNotSupportedError, match="COPY FROM not supported"):
        await _copy(application, [_record(_entry(CREATION, tenant="acme"))])
    async with owner.connect() as connection:
        assert len(list(await connection.execute(DEPLOYMENTS_ENTRIES))) == 3


@pytest.mark.postgres
async def test_the_maker_columns_and_the_events_maker_may_disagree(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    """The policy pins the type and the tenant, not who made it (ADR-0033)."""
    owner, application = engines
    entry = _entry(CREATION, tenant="acme")  # whose body names no maker
    forged = text(DEPLOYMENT_ENTRY.text.replace("'root'", "'mallory'"))
    async with _session(application, "acme") as session:
        await session.execute(forged, entry)
    async with owner.connect() as connection:
        makers = set(
            await connection.scalars(
                text("SELECT actor_id FROM grantr_audit WHERE tenant_id = '~deployment'")
            )
        )
        assert "mallory" in makers


@pytest.mark.postgres
async def test_a_connection_that_names_no_tenant_adds_no_creation_either(
    engines: tuple[AsyncEngine, AsyncEngine],
) -> None:
    """A pooled connection reads an empty tenant after a transaction, which matches no event's."""
    _, application = engines
    async with application.connect() as connection:
        await connection.execute(text("SELECT set_config('lattice.tenant_id', '', false)"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            await connection.execute(DEPLOYMENT_ENTRY, _entry(CREATION, tenant=""))
