"""The deployment's log is numbered in the order its entries commit, on PostgreSQL.

A tenant's creation adds its entry in the new tenant's transaction, which holds only that
tenant's lock. It takes the deployment log's lock first, as a change to the deployment does, so a
reader that has seen entry 11 never misses an entry 10 that commits later (grantr ADR-0033).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from grantr.core import DeploymentTenantCreated, User
from grantr.grants import Grants
from grantr.sql import SqlStorage, create_schema
from tests.catalogs import ARTIFACTR
from tests.databases import empty_database, row_level_security

ROOT = User(id="root")

BACKENDS = ["postgres", "postgres-rls"]


@asynccontextmanager
async def stores(backend: str, tmp_path: Any) -> AsyncIterator[tuple[Grants, SqlStorage]]:
    """grantr over PostgreSQL as its owner, or as a role its row-level security holds."""
    if backend == "postgres-rls":
        async with row_level_security() as (owner, application):
            storage = SqlStorage(application, row_level_security=True, across_tenants=owner)
            yield Grants(storage, catalogs=[ARTIFACTR]), storage
        return
    async with empty_database("postgres", tmp_path) as engine:
        await create_schema(engine)
        storage = SqlStorage(engine)
        yield Grants(storage, catalogs=[ARTIFACTR]), storage


@asynccontextmanager
async def paused_after_deployment_entry(
    storage: SqlStorage, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[asyncio.Event, asyncio.Event]]:
    """Make the next creation stop with its deployment entry added and its transaction open."""
    reached, release = asyncio.Event(), asyncio.Event()
    transaction = storage.transaction

    @asynccontextmanager
    async def pausing(tenant: str | None) -> AsyncIterator[Any]:
        async with transaction(tenant) as tx:
            append = tx.append

            async def appended(tenant: str | None, by: Any, event: Any) -> Any:
                entry = await append(tenant, by, event)
                if isinstance(event, DeploymentTenantCreated):
                    reached.set()
                    await release.wait()
                return entry

            monkeypatch.setattr(tx, "append", appended)
            yield tx

    monkeypatch.setattr(storage, "transaction", pausing)
    try:
        yield reached, release
    finally:
        monkeypatch.undo()


@pytest.mark.postgres
@pytest.mark.parametrize("backend", BACKENDS)
async def test_an_operators_change_waits_for_a_creation_and_is_numbered_after_it(
    backend: str, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with stores(backend, tmp_path) as (grants, storage):
        await grants.first_operator(ROOT.id)
        async with paused_after_deployment_entry(storage, monkeypatch) as (reached, release):
            creation = asyncio.create_task(grants.create_tenant("acme", owner="alice", by=ROOT))
            await asyncio.wait_for(reached.wait(), 10)
            monkeypatch.undo()  # the grant below runs as it is
            grant = asyncio.create_task(grants.grant_operator("bob", by=ROOT))
            await asyncio.sleep(0.5)
            waiting = not grant.done()
            release.set()  # even where the grant did not wait, so a failure does not hang
            assert waiting, "the grant waits for the creation to commit"
            created, granted = await asyncio.wait_for(asyncio.gather(creation, grant), 10)
        deployments = await grants.audit(None, by=ROOT)
        seqs = [entry.seq for entry in deployments]
        assert seqs == sorted(seqs)
        assert [entry.event.type for entry in deployments] == [
            "granted",
            "deployment_tenant_created",
            "granted",
        ]
        assert created.seq < granted.seq


@pytest.mark.postgres
@pytest.mark.parametrize("backend", BACKENDS)
async def test_concurrent_creations_and_operator_changes_all_commit_without_a_deadlock(
    backend: str, tmp_path: Any
) -> None:
    async with stores(backend, tmp_path) as (grants, _):
        await grants.first_operator(ROOT.id)
        work = [grants.create_tenant(f"t{i}", owner=f"owner{i}", by=ROOT) for i in range(6)]
        work += [grants.grant_operator(f"op{i}", by=ROOT) for i in range(6)]
        work += [grants.provision_tenant(f"p{i}", owner=f"owner{i}") for i in range(3)]
        await asyncio.wait_for(asyncio.gather(*work), 30)
        deployments = await grants.audit(None, by=ROOT, limit=100)
        assert len(deployments) == 1 + 6 + 6 + 3
        assert [e.seq for e in deployments] == sorted(e.seq for e in deployments)
        created = {
            e.event.tenant for e in deployments if isinstance(e.event, DeploymentTenantCreated)
        }
        assert created == {f"t{i}" for i in range(6)} | {f"p{i}" for i in range(3)}
