"""Fixtures for the diagrams' tests: artifactr's storages, under workspaces that take the
diagram type and its checks, gated by a switch the tests turn."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from artifactr.excalidraw import EXCALIDRAW_TYPES, excalidraw_checks, excalidraw_key_of
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import InMemoryStorage, Storage, Workspaces, integration_gate
from tests.databases import SQL_BACKENDS, empty_database
from tests.ui.toggles import Toggles


@pytest.fixture(params=["memory", *SQL_BACKENDS])
async def storage(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[Storage]:
    if request.param == "memory":
        yield InMemoryStorage()
        return
    async with empty_database(request.param, tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        yield SqlStorage(engine)


@pytest.fixture
def toggles() -> Toggles:
    return Toggles()


@pytest.fixture
def workspaces(storage: Storage, toggles: Toggles) -> Workspaces:
    return Workspaces(
        storage,
        types=EXCALIDRAW_TYPES,
        checks=excalidraw_checks(),
        gate=integration_gate(toggles, excalidraw_key_of),
    )
