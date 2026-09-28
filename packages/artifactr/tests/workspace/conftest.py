"""Fixtures for the workspace behaviour suite, parametrized over storage implementations."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tests.artifact_types  # noqa: F401  (registers the test artifact types)
from artifactr.core import UserActor
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import InMemoryStorage, Storage, Workspace, Workspaces
from tests.databases import SQL_BACKENDS, empty_database

ALICE = UserActor(id="alice", name="Alice")

Clock = Callable[[], datetime]
StorageFactory = Callable[[Clock], Storage]
"""Makes a storage with the given clock; every storage it makes shares one database."""


@pytest.fixture(params=["memory", *SQL_BACKENDS])
async def storage_factory(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[StorageFactory]:
    if request.param == "memory":
        yield lambda clock: InMemoryStorage(clock=clock)
        return
    async with empty_database(request.param, tmp_path) as engine:
        await create_schema(engine)
        yield lambda clock: SqlStorage(engine, clock=clock)


@pytest.fixture
def storage(storage_factory: StorageFactory) -> Storage:
    return storage_factory(lambda: datetime.now(UTC))


@pytest.fixture
def workspaces(storage: Storage) -> Workspaces:
    return Workspaces(storage)


@pytest.fixture
async def ws(workspaces: Workspaces) -> Workspace:
    return await workspaces.open("tenant_a", "ws_1", actor=ALICE)
