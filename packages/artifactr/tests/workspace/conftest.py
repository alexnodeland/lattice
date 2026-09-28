"""Fixtures for the workspace behaviour suite, parametrized over storage implementations."""

import pytest

import tests.artifact_types  # noqa: F401  (registers the test artifact types)
from artifactr.core import UserActor
from artifactr.workspace import InMemoryStorage, Storage, Workspace, Workspaces

ALICE = UserActor(id="alice", name="Alice")


@pytest.fixture(params=["memory"])
async def storage(request: pytest.FixtureRequest) -> Storage:
    assert request.param == "memory"
    return InMemoryStorage()


@pytest.fixture
def workspaces(storage: Storage) -> Workspaces:
    return Workspaces(storage)


@pytest.fixture
async def ws(workspaces: Workspaces) -> Workspace:
    return await workspaces.open("tenant_a", "ws_1", actor=ALICE)
