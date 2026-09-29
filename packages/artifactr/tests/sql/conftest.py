"""Fixtures for the SQL storage tests, parametrized over SQLite and PostgreSQL."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.databases import SQL_BACKENDS, empty_database


@pytest.fixture(params=SQL_BACKENDS)
async def engine(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """An engine on an empty database, with no tables."""
    async with empty_database(request.param, tmp_path) as engine:
        yield engine
