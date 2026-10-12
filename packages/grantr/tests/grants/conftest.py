"""Fixtures for the contract test, parametrized over storage implementations.

Every test that takes ``storage`` runs against memory, SQLite and, when it is configured,
PostgreSQL: as its owner, and as a role its row-level security holds.
"""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from grantr.core import User
from grantr.grants import Grants, InMemoryStorage, Storage
from grantr.sql import SqlStorage, create_schema
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR
from tests.databases import ROW_LEVEL_SECURITY, SQL_BACKENDS, empty_database, row_level_security

ROOT = User(id="root")
"""The deployment's first operator."""

ALICE = User(id="alice")
"""acme's owner."""

NOW = datetime(2026, 10, 12, tzinfo=UTC)

Clock = Callable[[], datetime]
StorageFactory = Callable[[Clock], Storage]


@pytest.fixture(params=["memory", *SQL_BACKENDS, ROW_LEVEL_SECURITY])
async def storage_factory(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[StorageFactory]:
    if request.param == "memory":
        yield lambda clock: InMemoryStorage(clock=clock)
        return
    if request.param == "postgres-rls":
        async with row_level_security() as (owner, application):
            yield lambda clock: SqlStorage(
                application, clock=clock, row_level_security=True, across_tenants=owner
            )
        return
    async with empty_database(request.param, tmp_path) as engine:
        await create_schema(engine)
        yield lambda clock: SqlStorage(engine, clock=clock)


@pytest.fixture
def storage(storage_factory: StorageFactory) -> Storage:
    return storage_factory(lambda: NOW)


@pytest.fixture
async def grants(storage: Storage) -> Grants:
    """grantr over the storage, with an operator, and acme owned by Alice."""
    grants = Grants(storage, catalogs=[ARTIFACTR, REFLEXR, PORTALR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    return grants
