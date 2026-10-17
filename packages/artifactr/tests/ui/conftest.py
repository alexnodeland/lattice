"""Fixtures for artifactr.ui's tests: artifactr's storages, memory, SQLite and, when configured,
PostgreSQL, under workspaces that take the forms layer's types and checks."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from artifactr.sql import SqlStorage, create_schema
from artifactr.ui import UI_TYPES, ui_checks
from artifactr.workspace import InMemoryStorage, Storage, Workspace, Workspaces
from tests.databases import SQL_BACKENDS, empty_database
from tests.ui.people import ADMIN


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
def workspaces(storage: Storage) -> Workspaces:
    async def is_admin(workspace: Workspace) -> bool:
        return workspace.actor == ADMIN

    return Workspaces(storage, types=UI_TYPES, checks=ui_checks(is_admin=is_admin))
