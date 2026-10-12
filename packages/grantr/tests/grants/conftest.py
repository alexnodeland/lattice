"""Fixtures for the contract test, parametrized over storage implementations.

Phase 3 adds SQLite and PostgreSQL to ``storage``'s parameters; every test that takes it then
runs against each.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from grantr.core import User
from grantr.grants import Grants, InMemoryStorage, Storage
from tests.catalogs import ARTIFACTR, PORTALR, REFLEXR

ROOT = User(id="root")
"""The deployment's first operator."""

ALICE = User(id="alice")
"""acme's owner."""

NOW = datetime(2026, 10, 12, tzinfo=UTC)

Clock = Callable[[], datetime]
StorageFactory = Callable[[Clock], Storage]


@pytest.fixture(params=["memory"])
def storage_factory(request: pytest.FixtureRequest) -> StorageFactory:
    assert request.param == "memory"
    return lambda clock: InMemoryStorage(clock=clock)


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
